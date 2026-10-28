from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import User, current_user
from ..db import session

router = APIRouter(prefix="/departments", tags=["departments"])
CURRENT = "9999-01-01"


@router.get("")
def list_departments(user: User = Depends(current_user)):
    with session(user, "list", "departments") as cur:
        cur.execute("""SELECT d.dept_no, d.dept_name, count(de.emp_no) AS headcount
                       FROM departments d
                       LEFT JOIN dept_emp de ON de.dept_no = d.dept_no AND de.to_date = %s
                       GROUP BY d.dept_no, d.dept_name ORDER BY d.dept_name""", (CURRENT,))
        return cur.fetchall()


@router.get("/{dept_no}")
def get_department(dept_no: str, user: User = Depends(current_user)):
    with session(user, "read", f"departments/{dept_no}") as cur:
        cur.execute("SELECT dept_no, dept_name FROM departments WHERE dept_no = %s", (dept_no,))
        dept = cur.fetchone()
        if not dept:
            raise HTTPException(404, "Department not found")
        cur.execute("""SELECT e.emp_no, e.first_name, e.last_name, dm.from_date, dm.to_date
                       FROM dept_manager dm JOIN employees e ON e.emp_no = dm.emp_no
                       WHERE dm.dept_no = %s ORDER BY dm.from_date DESC""", (dept_no,))
        dept["managers"] = cur.fetchall()
    return dept


@router.get("/{dept_no}/employees")
def department_employees(dept_no: str, page: int = Query(1, ge=1), page_size: int = Query(25, ge=1, le=100),
                         user: User = Depends(current_user)):
    with session(user, "list", f"departments/{dept_no}/employees", {"page": page}) as cur:
        cur.execute("""SELECT e.emp_no, e.first_name, e.last_name, t.title
                       FROM dept_emp de JOIN employees e ON e.emp_no = de.emp_no
                       LEFT JOIN titles t ON t.emp_no = e.emp_no AND t.to_date = %s
                       WHERE de.dept_no = %s AND de.to_date = %s
                       ORDER BY e.last_name, e.first_name LIMIT %s OFFSET %s""",
                    (CURRENT, dept_no, CURRENT, page_size, (page - 1) * page_size))
        return cur.fetchall()
