"""Integration tests need a real Postgres seeded by scripts/run_integration_tests.sh (RUN_INTEGRATION=1)."""
import os
from contextlib import contextmanager
from types import SimpleNamespace

import psycopg
import pytest
from fastapi.testclient import TestClient
from helpers import TEST_KEY, bearer, make_token
from psycopg.rows import dict_row


def pytest_collection_modifyitems(config, items):
    if os.getenv("RUN_INTEGRATION"):
        return
    skip = pytest.mark.skip(reason="integration test: run scripts/run_integration_tests.sh")
    for item in items:
        if "tests/integration" in str(item.fspath).replace("\\", "/"):
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _trust_test_key(monkeypatch):
    """Stand in for Keycloak's JWKS endpoint: the API trusts TEST_KEY's public half; everything else is real."""
    from app import auth

    monkeypatch.setattr(auth._jwks, "get_signing_key_from_jwt",
                        lambda _token: SimpleNamespace(key=TEST_KEY.public_key()))


@pytest.fixture(scope="session")
def client():
    from app.main import app

    with TestClient(app) as c:   # runs the lifespan: opens the DB pool
        yield c


@pytest.fixture
def hr():
    return bearer(make_token("it.alice", ["hr_admin", "employee"]))


@pytest.fixture
def mgr():  # current manager of d001 (Marketing)
    return bearer(make_token("it.bob", ["manager", "employee"], emp_no=110039))


@pytest.fixture
def emp():
    return bearer(make_token("it.carol", ["employee"], emp_no=10002))


@pytest.fixture
def hire_cleanup():
    """Employees created through the API must not outlive their test: other tests count every employee, and the
    API's DB user (correctly) cannot delete. Connects as the database owner; yields that connection for checks.
    Removes everything numbered above the highest employee that existed at the start, even if the test failed."""
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        pytest.skip("needs ADMIN_DATABASE_URL (set by scripts/run_integration_tests.sh) to clean up after itself")
    with psycopg.connect(url, autocommit=True) as conn:
        top = conn.execute("SELECT max(emp_no) FROM hr.employees").fetchone()[0]
        yield conn
        for table in ("salaries", "titles", "dept_emp", "employees"):   # children first (foreign keys)
            conn.execute(f"DELETE FROM hr.{table} WHERE emp_no > %s", (top,))


@pytest.fixture
def db_as():
    """Direct connection as the API's own DB user (portal_app), bypassing the API, with the caller's identity set."""
    @contextmanager
    def _ctx(role, emp_no=None):
        conn = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
        try:
            cur = conn.cursor()
            cur.execute("SELECT set_config('app.role', %s, true), set_config('app.emp_no', %s, true)",
                        (role, "" if emp_no is None else str(emp_no)))
            yield cur
        finally:
            conn.rollback()
            conn.close()
    return _ctx


# Employees the fake directory reports as HR admins. 10004 (Koblick, Finance) stands in for an HR colleague.
HR_ADMIN_EMP_NOS = {10004}


@pytest.fixture(autouse=True)
def fake_ldap(monkeypatch):
    """Stand in for the LDAP lookup (app/hr_lookup.py has its own unit tests). Tests may change `members`, or set
    `down = True` to simulate LDAP being unreachable."""
    from app.hr_lookup import HrLookupUnavailable
    from app.routers import hr_admin

    state = SimpleNamespace(members=set(HR_ADMIN_EMP_NOS), down=False, asked=[])

    def is_hr_admin(emp_no):
        state.asked.append(emp_no)
        if state.down:
            raise HrLookupUnavailable("test: LDAP down")
        return emp_no in state.members

    monkeypatch.setattr(hr_admin, "is_hr_admin", is_hr_admin)
    return state


@pytest.fixture
def salary_restore():
    """Salary changes made through the API must not outlive their test (other tests count salary rows, and the
    API's DB user cannot delete). Saves hr.salaries for the seeded employees and puts it back exactly afterwards.
    Yields the owner connection for checks."""
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        pytest.skip("needs ADMIN_DATABASE_URL (set by scripts/run_integration_tests.sh) to clean up after itself")
    with psycopg.connect(url, autocommit=True) as conn:
        saved = conn.execute("SELECT emp_no, salary, from_date, to_date FROM hr.salaries "
                             "WHERE emp_no <= 110114").fetchall()
        yield conn
        with conn.transaction():
            conn.execute("DELETE FROM hr.salaries WHERE emp_no <= 110114")
            with conn.cursor() as cur:
                cur.executemany("INSERT INTO hr.salaries VALUES (%s, %s, %s, %s)", saved)
