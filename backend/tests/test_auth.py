from contextlib import nullcontext
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import User, require_role, user_from_claims
from app.main import app

REQ = SimpleNamespace(method="GET", url=SimpleNamespace(path="/audit"))
client = TestClient(app)  # lifespan not started -> no DB needed


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize("path", ["/me", "/employees", "/departments", "/audit"])
def test_protected_routes_need_token(path):
    assert client.get(path).status_code == 401


def test_bad_token_rejected():
    r = client.get("/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_highest_role_wins():
    u = user_from_claims({"sub": "1", "preferred_username": "x", "emp_no": 5,
                          "realm_access": {"roles": ["employee", "manager"]}})
    assert (u.role, u.emp_no) == ("manager", 5)


def test_no_role_forbidden():
    with pytest.raises(HTTPException) as e:
        user_from_claims({"sub": "1", "realm_access": {"roles": ["offline_access"]}})
    assert e.value.status_code == 403


def test_require_role_blocks_manager_and_audits_the_denial(monkeypatch):
    import app.db as db

    calls = []

    def fake_session(*args):
        calls.append(args)
        return nullcontext()

    monkeypatch.setattr(db, "session", fake_session)
    with pytest.raises(HTTPException) as e:
        require_role("hr_admin")(REQ, User("1", "bob", "manager", 5))
    assert e.value.status_code == 403
    (user, action, resource, detail), = calls
    assert (user.username, action, resource) == ("bob", "denied", "audit")
    assert detail == {"method": "GET", "reason": "insufficient role", "required": ["hr_admin"]}


def test_require_role_allows_hr_admin():
    hr = User("2", "alice", "hr_admin", None)
    assert require_role("hr_admin")(REQ, hr) is hr


def test_denial_stays_403_even_if_the_audit_write_fails(monkeypatch):
    import app.db as db

    def boom(*_a, **_k):
        raise RuntimeError("database is down")

    monkeypatch.setattr(db, "session", boom)
    with pytest.raises(HTTPException) as e:
        require_role("hr_admin")(REQ, User("1", "bob", "manager", 5))
    assert e.value.status_code == 403
