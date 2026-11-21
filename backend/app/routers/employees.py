from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, current_user, require_role
from ..db import session

router = APIRouter(prefix="/employees", tags=["employees"])

CURRENT = "9999-01-01"
SORT_COLUMNS = {
    "name": ("e.last_name", "e.first_name"),
    "title": ("t.title", "e.last_name", "e.first_name"),
    "department": ("d.dept_name", "e.last_name", "e.first_name"),
    "hire_date": ("e.hire_date", "e.last_name", "e.first_name"),
}


@router.get("")
def search_employees(
    q: str | None = Query(None, min_length=2, description="Name substring"),
    dept_no: str | None = None,
    title: str | None = Query(None, description="Current title substring"),
    hired_from: date | None = Query(None, description="Hired on or after this date (inclusive)"),
    hired_to: date | None = Query(None, description="Hired on or before this date (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    sort_by: Literal["name", "title", "department", "hire_date"] = "name",
    sort_dir: Literal["asc", "desc"] = "asc",
    user: User = Depends(current_user),
):
    if hired_from and hired_to and hired_from > hired_to:
        raise HTTPException(422, "Hire date start must be on or before hire date end")
    where, params = [], {"cur": CURRENT, "limit": page_size, "offset": (page - 1) * page_size}
    if q:
        where.append("lower(e.first_name || ' ' || e.last_name) LIKE %(pat)s")
        params["pat"] = f"%{q.lower()}%"
    if dept_no:
        where.append("de.dept_no = %(dept)s")
        params["dept"] = dept_no
    if title:
        where.append("lower(t.title) LIKE %(title)s")
        params["title"] = f"%{title.lower()}%"
    if hired_from:
        where.append("e.hire_date >= %(hired_from)s")
        params["hired_from"] = hired_from
    if hired_to:
        where.append("e.hire_date <= %(hired_to)s")
        params["hired_to"] = hired_to
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"""FROM employees e
      LEFT JOIN dept_emp de ON de.emp_no = e.emp_no AND de.to_date = %(cur)s
      LEFT JOIN departments d ON d.dept_no = de.dept_no
      LEFT JOIN titles t ON t.emp_no = e.emp_no AND t.to_date = %(cur)s {clause}"""
    # Only allowlisted columns and validated directions enter the SQL ordering.
    order = ", ".join(f"{column} {sort_dir.upper()} NULLS LAST" for column in SORT_COLUMNS[sort_by])
    order += ", e.emp_no ASC"
    with session(user, "search", "employees", {"q": q, "dept_no": dept_no, "page": page,
                                               "title": title,
                                               "hired_from": hired_from.isoformat() if hired_from else None,
                                               "hired_to": hired_to.isoformat() if hired_to else None,
                                               "sort_by": sort_by, "sort_dir": sort_dir}) as cur:
        cur.execute(f"SELECT e.emp_no, e.first_name, e.last_name, e.hire_date, d.dept_no, d.dept_name, t.title "
                    f"{base} ORDER BY {order} LIMIT %(limit)s OFFSET %(offset)s", params)
        items = cur.fetchall()
        cur.execute(f"SELECT count(*) AS n {base}", params)
        total = cur.fetchone()["n"]
    return {"items": items, "total": total, "page": page, "page_size": page_size}


@router.get("/{emp_no}")
def get_employee(emp_no: int, user: User = Depends(current_user)):
    with session(user, "read", f"employees/{emp_no}") as cur:
        cur.execute("""SELECT e.emp_no, e.first_name, e.last_name, e.gender, e.hire_date, e.birth_date,
                              d.dept_no, d.dept_name, t.title
                       FROM employees e
                       LEFT JOIN dept_emp de ON de.emp_no = e.emp_no AND de.to_date = %s
                       LEFT JOIN departments d ON d.dept_no = de.dept_no
                       LEFT JOIN titles t ON t.emp_no = e.emp_no AND t.to_date = %s
                       WHERE e.emp_no = %s""", (CURRENT, CURRENT, emp_no))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Employee not found")
    if user.role == "employee":          # basic directory only
        row.pop("birth_date", None)
        row.pop("gender", None)
    return row


@router.get("/{emp_no}/titles")
def title_history(emp_no: int, user: User = Depends(current_user)):
    with session(user, "read", f"employees/{emp_no}/titles") as cur:
        cur.execute("SELECT title, from_date, to_date FROM titles WHERE emp_no = %s ORDER BY from_date DESC", (emp_no,))
        return cur.fetchall()


@router.get("/{emp_no}/salaries")
def salary_history(emp_no: int, user: User = Depends(require_role("manager", "hr_admin"))):
    # API check above + Postgres RLS: a manager asking about someone outside their dept gets 0 rows -> 404.
    with session(user, "read", f"employees/{emp_no}/salaries") as cur:
        cur.execute("SELECT salary, from_date, to_date FROM salaries WHERE emp_no = %s ORDER BY from_date DESC", (emp_no,))
        rows = cur.fetchall()
    if not rows:
        raise HTTPException(404, "No salary data visible")
    return rows
