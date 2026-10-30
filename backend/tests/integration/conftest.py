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
