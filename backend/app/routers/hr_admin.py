"""HR-admin-only operations: hiring and salary changes. Every route here needs the hr_admin role. The router itself
carries that requirement, so a route added later is protected by default, and Postgres row-level security
independently refuses the same writes for any other role (db/post/04_hr_write_access.sql, 05_hr_salary_adjust.sql)."""
from datetime import date, timedelta
from typing import Literal

import psycopg.errors
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from ..auth import User, require_role
from ..db import session, write_audit
from ..hr_lookup import HrLookupUnavailable, is_hr_admin

CURRENT = "9999-01-01"   # "still current" marker used throughout the dataset

# Titles HR can give a new hire. "Manager" is left out on purpose: managing a department is a separate record
# (dept_manager) that this flow does not create, and the manager-scoped salary rules depend on that record.
HIRE_TITLES = ("Assistant Engineer", "Engineer", "Senior Engineer", "Staff", "Senior Staff", "Technique Leader")

# Sanity limits that catch typos (an extra zero, a wrong century). They are not HR policy.
MIN_HIRE_AGE = 16
MAX_DAYS_AHEAD = 366     # a hire or a salary change may be entered up to a year before it takes effect
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


# ---------- Salary changes ----------
# A change adds the new salary (effective date -> '9999-01-01') and closes the current one (its to_date becomes
# the effective date), in one transaction. Rules, each also enforced in Postgres except the LDAP one:
#   * no change to your own salary, nor to another HR admin's (LDAP hr-admins group, checked live, fails closed);
#   * the effective date is today or later (history is never rewritten), at most a year ahead, and after the
#     current salary started;
#   * at most one pending change: if the current salary itself starts in the future, nothing more can be added.

class SalaryChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    salary: int = Field(ge=1, le=MAX_SALARY)
    effective_date: date

    @field_validator("effective_date")
    @classmethod
    def _today_to_a_year_ahead(cls, value: date) -> date:
        if value < date.today():
            raise ValueError("cannot be in the past")
        if value > date.today() + timedelta(days=MAX_DAYS_AHEAD):
            raise ValueError("cannot be more than a year in the future")
        return value


def _who_blocks(user: User, emp_no: int) -> str | None:
    """Why this HR admin may not change this employee's salary, or None if they may.
    Raises HTTPException(503) when LDAP cannot be asked (the change is refused, never allowed)."""
    if user.emp_no is not None and user.emp_no == emp_no:
        return "own salary"
    try:
        if is_hr_admin(emp_no):
            return "target is an HR admin"
    except HrLookupUnavailable as exc:
        raise HTTPException(503, "Cannot check whether this employee is an HR admin right now, so salary "
                                 "changes are unavailable. Try again later.") from exc
    return None


BLOCK_MESSAGES = {
    "own salary": "You cannot change your own salary.",
    "target is an HR admin": "HR admins cannot change the salary of another HR admin.",
}


def _current_and_pending(cur, emp_no: int, lock: bool = False):
    """The open ('9999-01-01') salary row, or None. With lock=True it is locked until the transaction ends, so two
    simultaneous changes for one employee run one after the other instead of both closing the same row."""
    cur.execute("SELECT salary, from_date, to_date FROM salaries WHERE emp_no = %s AND to_date = %s"
                + (" FOR UPDATE" if lock else ""), (emp_no, CURRENT))
    return cur.fetchone()


@router.get("/employees/{emp_no}/salary-change")
def salary_change_status(emp_no: int, user: User = Depends(ONLY_HR)):
    """What the salary-change form needs: whether a change is allowed, the current salary and any pending change."""
    with session(user, "read", f"hr/employees/{emp_no}/salary-change") as cur:
        cur.execute("SELECT 1 FROM employees WHERE emp_no = %s", (emp_no,))
        if cur.fetchone() is None:
            raise HTTPException(404, "Employee not found")
        open_row = _current_and_pending(cur, emp_no)
        cur.execute("SELECT salary, from_date, to_date FROM salaries WHERE emp_no = %s AND from_date <= %s "
                    "ORDER BY from_date DESC LIMIT 1", (emp_no, date.today()))
        in_effect = cur.fetchone()
    pending = open_row if open_row and open_row["from_date"] > date.today() else None
    blocked = _who_blocks(user, emp_no)
    reason = BLOCK_MESSAGES.get(blocked or "")
    if reason is None and open_row is None:
        reason = "This employee has no current salary (they may have left), so it cannot be changed."
    elif reason is None and pending is not None:
        reason = f"A salary change is already pending (from {pending['from_date']}). Only one can be pending."
    earliest = max(date.today(), open_row["from_date"] + timedelta(days=1)) if open_row else date.today()
    return {"can_change": reason is None, "reason": reason, "current": in_effect, "pending": pending,
            "earliest_date": earliest, "latest_date": date.today() + timedelta(days=MAX_DAYS_AHEAD)}


def _field_error(field: str, msg: str) -> HTTPException:
    return HTTPException(422, [{"type": "value_error", "loc": ["body", field], "msg": msg}])


@router.post("/employees/{emp_no}/salaries", status_code=201)
def change_salary(emp_no: int, body: SalaryChange, user: User = Depends(ONLY_HR)):
    resource = f"employees/{emp_no}/salaries"
    blocked = _who_blocks(user, emp_no)       # asks LDAP before the transaction, so no row is locked meanwhile
    if blocked:
        with session(user, "denied", resource, {"method": "POST", "reason": blocked}):
            pass
        raise HTTPException(403, BLOCK_MESSAGES[blocked])
    try:
        with session(user, "update", resource, audit=False) as cur:
            current = _current_and_pending(cur, emp_no, lock=True)
            if current is None:
                cur.execute("SELECT 1 FROM employees WHERE emp_no = %s", (emp_no,))
                if cur.fetchone() is None:
                    raise HTTPException(404, "Employee not found")
                raise HTTPException(409, "This employee has no current salary (they may have left, or it was "
                                         "changed a moment ago). Reload and try again.")
            if current["from_date"] > date.today():
                raise HTTPException(409, f"A salary change is already pending (from {current['from_date']}). "
                                         "Only one can be pending.")
            if body.effective_date <= current["from_date"]:
                raise _field_error("effective_date", f"must be after {current['from_date']}, when the current "
                                                     "salary started")
            if body.salary == current["salary"]:
                raise _field_error("salary", "is the same as the current salary")
            cur.execute("INSERT INTO salaries (emp_no, salary, from_date, to_date) VALUES (%s, %s, %s, %s)",
                        (emp_no, body.salary, body.effective_date, CURRENT))
            cur.execute("UPDATE salaries SET to_date = %s WHERE emp_no = %s AND from_date = %s AND to_date = %s",
                        (body.effective_date, emp_no, current["from_date"], CURRENT))
            if cur.rowcount != 1:      # cannot happen while the row is locked; never commit a half change
                raise HTTPException(409, "The current salary changed a moment ago. Reload and try again.")
            # Like hiring, the log records who changed whose salary and when it takes effect, not the amounts.
            write_audit(cur, user, "update", resource, {"effective_date": body.effective_date.isoformat()})
    except (psycopg.errors.UniqueViolation, psycopg.errors.ExclusionViolation) as exc:
        raise HTTPException(409, "The salary changed a moment ago. Reload and try again.") from exc
    except psycopg.errors.InsufficientPrivilege as exc:
        raise HTTPException(403, "The database refused this salary change.") from exc
    except psycopg.errors.CheckViolation as exc:
        raise HTTPException(409, exc.diag.message_primary or "The database refused this salary change.") from exc
    return {"emp_no": emp_no, "salary": body.salary, "from_date": body.effective_date, "to_date": CURRENT,
            "previous": {"salary": current["salary"], "from_date": current["from_date"],
                         "to_date": body.effective_date}}
