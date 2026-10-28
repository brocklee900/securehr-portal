from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, current_user, require_role
from ..db import session

router = APIRouter(prefix="/employees", tags=["employees"])

CURRENT = "9999-01-01"


@router.get("")
def search_employees(
    q: str | None = Query(None, min_length=2, description="Name substring"),
    dept_no: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    user: User = Depends(current_user),
):
    where, params = [], {"cur": CURRENT, "limit": page_size, "offset": (page - 1) * page_size}
    if q:
        where.append("lower(e.first_name || ' ' || e.last_name) LIKE %(pat)s")
        params["pat"] = f"%{q.lower()}%"
    if dept_no:
        where.append("de.dept_no = %(dept)s")
        params["dept"] = dept_no
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    base = f"""FROM employees e
      LEFT JOIN dept_emp de ON de.emp_no = e.emp_no AND de.to_date = %(cur)s
      LEFT JOIN departments d ON d.dept_no = de.dept_no
      LEFT JOIN titles t ON t.emp_no = e.emp_no AND t.to_date = %(cur)s {clause}"""
    with session(user, "search", "employees", {"q": q, "dept_no": dept_no, "page": page}) as cur:
        cur.execute(f"SELECT e.emp_no, e.first_name, e.last_name, e.hire_date, d.dept_no, d.dept_name, t.title "
                    f"{base} ORDER BY e.last_name, e.first_name, e.emp_no LIMIT %(limit)s OFFSET %(offset)s", params)
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
