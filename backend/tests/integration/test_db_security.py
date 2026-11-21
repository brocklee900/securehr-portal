"""Row-level security checked directly in Postgres as the API's own DB user, with the API out of the picture."""
import os

import psycopg
import pytest

TOTAL_SALARY_ROWS = 16          # see seed.sql
MARKETING_PEOPLE = {10001, 10002, 110022, 110039}
FINANCE_PEOPLE = {10003, 10004, 10005, 110114}
SEED_ROW_COUNTS = {"employees": 8, "dept_emp": 9, "titles": 10}   # see seed.sql

# One INSERT per table a new hire touches (the rows are valid, so only permissions can stop them).
HIRE_INSERTS = {
    "employees": "INSERT INTO hr.employees VALUES (900001, '1990-01-01', 'Eve', 'Intruder', 'F', '2030-01-01')",
    "dept_emp": "INSERT INTO hr.dept_emp VALUES (10001, 'd003', '2030-01-01', '9999-01-01')",
    "titles": "INSERT INTO hr.titles VALUES (10001, 'Staff', '2031-01-01', '9999-01-01')",
    "salaries": "INSERT INTO hr.salaries VALUES (10001, 1, '2031-01-01', '9999-01-01')",
}


def visible_salary_emps(cur):
    cur.execute("SELECT DISTINCT emp_no FROM hr.salaries")
    return {r["emp_no"] for r in cur.fetchall()}


def test_app_role_cannot_bypass_rls():
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        row = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'portal_app'").fetchone()
    assert row == (False, False)


@pytest.mark.parametrize("role", ["employee", "", "admin", "HR_ADMIN"])
def test_unprivileged_or_unknown_roles_see_no_salaries(db_as, role):
    with db_as(role, emp_no=110039) as cur:
        assert visible_salary_emps(cur) == set()


def test_hr_admin_sees_every_salary(db_as):
    with db_as("hr_admin") as cur:
        cur.execute("SELECT count(*) AS n FROM hr.salaries")
        assert cur.fetchone()["n"] == TOTAL_SALARY_ROWS


def test_manager_sees_only_current_department(db_as):
    with db_as("manager", emp_no=110039) as cur:
        assert visible_salary_emps(cur) == MARKETING_PEOPLE
    with db_as("manager", emp_no=110114) as cur:
        assert visible_salary_emps(cur) == FINANCE_PEOPLE


def test_former_or_missing_manager_sees_nothing(db_as):
    with db_as("manager", emp_no=110022) as cur:      # managed Marketing until 1991
        assert visible_salary_emps(cur) == set()
    with db_as("manager", emp_no=None) as cur:
        assert visible_salary_emps(cur) == set()


@pytest.mark.parametrize("sql", [
    "UPDATE hr.salaries SET salary = 1", "DELETE FROM hr.salaries",
    "UPDATE hr.employees SET first_name = 'x'", "DELETE FROM hr.employees",
    "UPDATE hr.titles SET title = 'x'", "DELETE FROM hr.titles",
    "UPDATE hr.dept_emp SET dept_no = 'd003'", "DELETE FROM hr.dept_emp",
])
def test_app_role_cannot_update_or_delete_hr_data_even_as_hr_admin(db_as, sql):
    """Hiring adds rows; it must never let the app rewrite or erase history."""
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)


@pytest.mark.parametrize("sql", [
    "INSERT INTO hr.departments VALUES ('d009', 'Skunkworks')",
    "INSERT INTO hr.dept_manager VALUES (10001, 'd003', '2030-01-01', '9999-01-01')",
])
def test_app_role_cannot_create_departments_or_managers_even_as_hr_admin(db_as, sql):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)


def test_hr_admin_can_insert_a_new_employee_in_all_four_tables(db_as):
    with db_as("hr_admin") as cur:   # rolled back by db_as afterwards
        cur.execute("SELECT nextval('hr.employees_emp_no_seq') AS n")
        n = cur.fetchone()["n"]
        cur.execute("INSERT INTO hr.employees VALUES (%s, '1990-01-01', 'Ada', 'Lovelace', 'F', '2030-01-01')", (n,))
        cur.execute("INSERT INTO hr.dept_emp VALUES (%s, 'd003', '2030-01-01', '9999-01-01')", (n,))
        cur.execute("INSERT INTO hr.titles VALUES (%s, 'Engineer', '2030-01-01', '9999-01-01')", (n,))
        cur.execute("INSERT INTO hr.salaries VALUES (%s, 50000, '2030-01-01', '9999-01-01')", (n,))
        cur.execute("SELECT count(*) AS n FROM hr.salaries WHERE emp_no = %s", (n,))
        assert cur.fetchone()["n"] == 1


@pytest.mark.parametrize("table", HIRE_INSERTS)
@pytest.mark.parametrize("role", ["employee", "manager", "", "admin", "HR_ADMIN"])
def test_only_hr_admin_can_insert_hr_rows(db_as, role, table):
    with db_as(role, emp_no=110039) as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(HIRE_INSERTS[table])


@pytest.mark.parametrize("role", ["employee", "manager", ""])
def test_directory_tables_stay_readable_by_every_role(db_as, role):
    """Row-level security is now on employees, dept_emp and titles too; reading them must be unaffected."""
    counts = {}
    with db_as(role, emp_no=110039) as cur:
        for table in SEED_ROW_COUNTS:
            cur.execute(f"SELECT count(*) AS n FROM hr.{table}")
            counts[table] = cur.fetchone()["n"]
    assert counts == SEED_ROW_COUNTS


def test_employee_numbers_continue_after_the_highest_and_cannot_be_reset(db_as):
    with db_as("hr_admin") as cur:
        cur.execute("SELECT nextval('hr.employees_emp_no_seq') AS n, (SELECT max(emp_no) FROM hr.employees) AS top")
        row = cur.fetchone()
        assert row["n"] > row["top"]
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute("SELECT setval('hr.employees_emp_no_seq', 1)")


def test_audit_log_is_append_only_and_readable_only_by_hr(db_as):
    with db_as("employee") as cur:
        cur.execute("INSERT INTO app.audit_log (username, role, action, resource) VALUES ('it.db', 'employee', 'read', 'x')")
        cur.execute("SELECT count(*) AS n FROM app.audit_log")
        assert cur.fetchone()["n"] == 0                       # may append, may not read
    with db_as("manager", emp_no=110039) as cur:
        cur.execute("SELECT count(*) AS n FROM app.audit_log")
        assert cur.fetchone()["n"] == 0
    with db_as("hr_admin") as cur:
        cur.execute("INSERT INTO app.audit_log (username, role, action, resource) VALUES ('it.db', 'hr_admin', 'read', 'x')")
        cur.execute("SELECT count(*) AS n FROM app.audit_log")
        assert cur.fetchone()["n"] >= 1


@pytest.mark.parametrize("sql", ["UPDATE app.audit_log SET username = 'x'", "DELETE FROM app.audit_log"])
def test_nobody_can_edit_or_delete_audit_entries(db_as, sql):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)
