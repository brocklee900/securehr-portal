import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth import user_from_claims
from app.main import app

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
