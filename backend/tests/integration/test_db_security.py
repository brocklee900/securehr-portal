"""Row-level security checked directly in Postgres as the API's own DB user, with the API out of the picture."""
import os

import psycopg
import pytest

TOTAL_SALARY_ROWS = 16          # see seed.sql
MARKETING_PEOPLE = {10001, 10002, 110022, 110039}
FINANCE_PEOPLE = {10003, 10004, 10005, 110114}


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
    "UPDATE hr.salaries SET salary = 1",
    "DELETE FROM hr.salaries",
    "INSERT INTO hr.salaries VALUES (10001, 1, '2030-01-01', '2031-01-01')",
    "UPDATE hr.employees SET first_name = 'x'",
])
def test_app_role_cannot_modify_hr_data_even_as_hr_admin(db_as, sql):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)


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
