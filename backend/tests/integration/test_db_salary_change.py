"""The salary-change rules in Postgres (db/post/05_hr_salary_adjust.sql), checked directly as the API's own DB
user with the API out of the picture. Every test runs inside db_as, which rolls back."""
from datetime import date, timedelta

import psycopg
import pytest

TODAY = date.today()
OPEN = "9999-01-01"


def add(cur, emp_no=10001, salary=95000, start=TODAY):
    cur.execute("INSERT INTO hr.salaries VALUES (%s, %s, %s, %s)", (emp_no, salary, start, OPEN))


def close(cur, emp_no=10001, end=TODAY, from_date="2001-06-22"):
    cur.execute("UPDATE hr.salaries SET to_date = %s WHERE emp_no = %s AND from_date = %s", (end, emp_no, from_date))
    return cur.rowcount


def commit_checks(cur):
    cur.execute("SET CONSTRAINTS ALL IMMEDIATE")   # run the deferred (commit-time) checks now


def test_hr_admin_can_add_a_salary_and_close_the_current_one(db_as):
    with db_as("hr_admin") as cur:
        add(cur)
        assert close(cur) == 1
        commit_checks(cur)
        cur.execute("SELECT salary, to_date FROM hr.salaries WHERE emp_no = 10001 ORDER BY from_date DESC LIMIT 2")
        assert [(r["salary"], r["to_date"]) for r in cur.fetchall()] == [(95000, date(9999, 1, 1)), (88958, TODAY)]


def test_a_future_change_is_allowed(db_as):
    later = TODAY + timedelta(days=60)
    with db_as("hr_admin") as cur:
        add(cur, start=later)
        assert close(cur, end=later) == 1
        commit_checks(cur)


@pytest.mark.parametrize("sql", [
    "UPDATE hr.salaries SET salary = 1 WHERE emp_no = 10001",
    "UPDATE hr.salaries SET from_date = '2001-06-23' WHERE emp_no = 10001",
    "UPDATE hr.salaries SET emp_no = 10002 WHERE emp_no = 10001",
    "DELETE FROM hr.salaries WHERE emp_no = 10001",
])
def test_only_the_end_date_can_ever_change(db_as, sql):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        cur.execute(sql)


@pytest.mark.parametrize("role", ["employee", "manager", "", "admin", "HR_ADMIN"])
def test_only_hr_admin_can_close_a_salary(db_as, role):
    with db_as(role, emp_no=110039) as cur:      # 110039 manages 10001's department and can read the row
        assert close(cur) == 0


def test_a_past_salary_cannot_be_reopened_or_moved(db_as):
    with db_as("hr_admin") as cur:       # row-level security only exposes the open row to UPDATE
        assert close(cur, from_date="1986-06-26", end="1990-01-01") == 0
        cur.execute("UPDATE hr.salaries SET to_date = %s WHERE emp_no = 10001 AND to_date <> %s", (OPEN, OPEN))
        assert cur.rowcount == 0


def test_closing_needs_the_replacement_to_exist(db_as):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.CheckViolation, match="before closing"):
        close(cur)


@pytest.mark.parametrize("end", [TODAY - timedelta(days=1), date(2001, 6, 22), date(1999, 1, 1)])
def test_history_cannot_be_rewritten_with_a_past_end_date(db_as, end):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.CheckViolation):
        close(cur, end=end)


@pytest.mark.parametrize("start,end", [(TODAY - timedelta(days=1), OPEN), (TODAY, "2040-01-01")])
def test_an_existing_employee_only_gets_a_new_current_salary_from_today_on(db_as, start, end):
    with db_as("hr_admin") as cur, pytest.raises(psycopg.errors.CheckViolation):
        cur.execute("INSERT INTO hr.salaries VALUES (10001, 95000, %s, %s)", (start, end))


def test_a_second_pending_change_is_refused(db_as):
    later = TODAY + timedelta(days=30)
    with db_as("hr_admin") as cur:
        add(cur, start=later)
        close(cur, end=later)
        add(cur, salary=99000, start=later + timedelta(days=10))
        with pytest.raises(psycopg.errors.CheckViolation, match="already has a pending"):
            close(cur, end=later + timedelta(days=10), from_date=later)


def test_two_current_salaries_are_refused_at_commit(db_as):
    with db_as("hr_admin") as cur:
        add(cur)                                    # new open row, old one never closed
        with pytest.raises(psycopg.errors.ExclusionViolation):
            commit_checks(cur)


def test_nobody_can_change_their_own_salary_in_the_database(db_as):
    with db_as("hr_admin", emp_no=10001) as cur, pytest.raises(psycopg.errors.InsufficientPrivilege):
        add(cur)


def test_a_new_hires_first_salary_may_still_start_in_the_past(db_as):
    with db_as("hr_admin") as cur:
        cur.execute("SELECT nextval('hr.employees_emp_no_seq') AS n")
        n = cur.fetchone()["n"]
        cur.execute("INSERT INTO hr.employees VALUES (%s, '1990-01-01', 'Ada', 'Lovelace', 'F', '2020-01-01')", (n,))
        cur.execute("INSERT INTO hr.salaries VALUES (%s, 50000, '2020-01-01', %s)", (n, OPEN))
        commit_checks(cur)
