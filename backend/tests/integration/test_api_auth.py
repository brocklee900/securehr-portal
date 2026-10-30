import time

import pytest
from helpers import OTHER_KEY, bearer, make_token


def test_missing_token_is_401(client):
    assert client.get("/me").status_code == 401


def test_garbage_token_is_401(client):
    assert client.get("/me", headers=bearer("not.a.jwt")).status_code == 401


def test_expired_token_is_401(client):
    token = make_token("it.x", ["employee"], exp=int(time.time()) - 60)
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_wrong_audience_is_401(client):
    assert client.get("/me", headers=bearer(make_token("it.x", ["employee"], aud="some-other-app"))).status_code == 401


def test_wrong_issuer_is_401(client):
    token = make_token("it.x", ["employee"], iss="https://evil.example/realms/securehr")
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_token_signed_with_untrusted_key_is_401(client):
    assert client.get("/me", headers=bearer(make_token("it.x", ["hr_admin"], key=OTHER_KEY))).status_code == 401


def test_alg_none_token_is_401(client):
    token = make_token("it.x", ["hr_admin"], key="", algorithm="none")
    assert client.get("/me", headers=bearer(token)).status_code == 401


def test_valid_token_without_portal_role_is_403(client):
    assert client.get("/me", headers=bearer(make_token("it.x", []))).status_code == 403


def test_me_reports_identity(client, mgr):
    assert client.get("/me", headers=mgr).json() == {"username": "it.bob", "role": "manager", "emp_no": 110039}


def test_highest_role_wins(client):
    token = make_token("it.x", ["employee", "manager", "hr_admin"])
    assert client.get("/me", headers=bearer(token)).json()["role"] == "hr_admin"


@pytest.mark.parametrize("path", ["/employees", "/employees/10001", "/employees/10001/titles",
                                  "/employees/10001/salaries", "/departments", "/departments/d001",
                                  "/departments/d001/employees", "/audit"])
def test_every_data_endpoint_requires_login(client, path):
    assert client.get(path).status_code == 401
