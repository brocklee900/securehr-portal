"""HR-admin-only operations (currently: hiring). Every route here needs the hr_admin role. The router itself
carries that requirement, so a route added later is protected by default, and Postgres row-level security
independently refuses the same writes for any other role (db/post/04_hr_write_access.sql)."""
from datetime import date, timedelta
from typing import Literal

import psycopg.errors
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from ..auth import User, require_role
from ..db import session, write_audit

CURRENT = "9999-01-01"   # "still current" marker used throughout the dataset

# Titles HR can give a new hire. "Manager" is left out on purpose: managing a department is a separate record
# (dept_manager) that this flow does not create, and the manager-scoped salary rules depend on that record.
HIRE_TITLES = ("Assistant Engineer", "Engineer", "Senior Engineer", "Staff", "Senior Staff", "Technique Leader")

# Sanity limits that catch typos (an extra zero, a wrong century). They are not HR policy.
MIN_HIRE_AGE = 16
MAX_DAYS_AHEAD = 366     # a hire may be entered up to a year before the start date
MAX_SALARY = 1_000_000
EARLIEST_BIRTH = date(1900, 1, 1)

ONLY_HR = require_role("hr_admin")
router = APIRouter(prefix="/hr", tags=["hr-admin"], dependencies=[Depends(ONLY_HR)])


def _age_on(day: date, born: date) -> int:
    return day.year - born.year - ((day.month, day.day) < (born.month, born.day))


class NewEmployee(BaseModel):
    """Everything needed to fill one employee across employees, dept_emp, titles and salaries.
    emp_no is deliberately not accepted (extra fields are rejected): the database assigns it."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    first_name: str = Field(min_length=1, max_length=14)   # the migrated columns are varchar(14) / varchar(16)
    last_name: str = Field(min_length=1, max_length=16)
    gender: Literal["M", "F"]
    birth_date: date
    hire_date: date
    dept_no: str = Field(pattern=r"^d\d{3}$")
    title: str
    salary: int = Field(ge=1, le=MAX_SALARY)

    @field_validator("first_name", "last_name")
    @classmethod
    def _no_control_characters(cls, value: str) -> str:
        if not value.isprintable():
            raise ValueError("must not contain control characters")
        return value

    @field_validator("title")
    @classmethod
    def _assignable_title(cls, value: str) -> str:
        if value not in HIRE_TITLES:
            raise ValueError("must be one of: " + ", ".join(HIRE_TITLES))
        return value

    @field_validator("birth_date")
    @classmethod
    def _plausible_birth_date(cls, value: date) -> date:
        if not EARLIEST_BIRTH <= value <= date.today():
            raise ValueError(f"must be between {EARLIEST_BIRTH} and today")
        return value

    @field_validator("hire_date")
    @classmethod
    def _plausible_hire_date(cls, value: date, info: ValidationInfo) -> date:
        if value > date.today() + timedelta(days=MAX_DAYS_AHEAD):
            raise ValueError("cannot be more than a year in the future")
        born = info.data.get("birth_date")   # absent if birth_date itself was invalid (already reported)
        if born is not None and _age_on(value, born) < MIN_HIRE_AGE:
            raise ValueError(f"employee must be at least {MIN_HIRE_AGE} on the hire date")
        return value


@router.get("/titles")
def hire_titles() -> list[str]:
    """Titles that can be given to a new hire (feeds the form's dropdown and matches the server-side check)."""
    return list(HIRE_TITLES)


@router.post("/employees", status_code=201)
def create_employee(body: NewEmployee, user: User = Depends(ONLY_HR)):
    """Create an employee: one row in each of employees, dept_emp, titles and salaries, all in one transaction
    (everything is saved or nothing is). Start dates all equal the hire date and end dates use the dataset's
    "current" marker, which is how every existing employee's current department, title and salary are stored."""
    try:
        with session(user, "create", "employees", audit=False) as cur:
            cur.execute("SELECT dept_name FROM departments WHERE dept_no = %s", (body.dept_no,))
            dept = cur.fetchone()
            if dept is None:
                raise HTTPException(422, [{"type": "value_error", "loc": ["body", "dept_no"],
                                           "msg": "Unknown department"}])
            cur.execute("SELECT nextval('hr.employees_emp_no_seq') AS emp_no")
            emp_no = cur.fetchone()["emp_no"]
            cur.execute("INSERT INTO employees (emp_no, birth_date, first_name, last_name, gender, hire_date) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (emp_no, body.birth_date, body.first_name, body.last_name, body.gender, body.hire_date))
            cur.execute("INSERT INTO dept_emp (emp_no, dept_no, from_date, to_date) VALUES (%s, %s, %s, %s)",
                        (emp_no, body.dept_no, body.hire_date, CURRENT))
            cur.execute("INSERT INTO titles (emp_no, title, from_date, to_date) VALUES (%s, %s, %s, %s)",
                        (emp_no, body.title, body.hire_date, CURRENT))
            cur.execute("INSERT INTO salaries (emp_no, salary, from_date, to_date) VALUES (%s, %s, %s, %s)",
                        (emp_no, body.salary, body.hire_date, CURRENT))
            # The log records who created whom and where, but not personal data (names, birth date, salary).
            write_audit(cur, user, "create", f"employees/{emp_no}",
                        {"dept_no": body.dept_no, "title": body.title})
    except psycopg.errors.UniqueViolation as exc:
        raise HTTPException(409, "Employee number already in use: the numbering sequence is behind the data. "
                                 "Re-run db/post/04_hr_write_access.sql.") from exc
    return {"emp_no": emp_no, **body.model_dump(), "dept_name": dept["dept_name"]}
