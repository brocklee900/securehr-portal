import uuid

from helpers import bearer, make_token


def unique(prefix):
    """Fresh username per test run, so counts stay exact even on a database that has been used before."""
    return f"{prefix}.{uuid.uuid4().hex[:8]}"


def audit(client, headers, **params):
    return client.get("/audit", params=params, headers=headers)


def test_only_hr_admin_can_read_the_log(client, hr, mgr, emp):
    assert audit(client, hr).status_code == 200
    assert audit(client, mgr).status_code == 403
    assert audit(client, emp).status_code == 403


def test_actions_are_recorded_with_who_what_and_detail(client, hr):
    name = unique("it.audit.user1")
    user = bearer(make_token(name, ["employee"]))
    client.get("/employees", params={"q": "koblick"}, headers=user)
    client.get("/employees/10001", headers=user)
    body = audit(client, hr, username=name).json()
    assert body["total"] >= 2
    seen = {(r["action"], r["resource"]) for r in body["items"]}
    assert ("search", "employees") in seen and ("read", "employees/10001") in seen
    search_row = next(r for r in body["items"] if r["action"] == "search")
    assert search_row["role"] == "employee" and search_row["detail"]["q"] == "koblick"


def test_reading_the_audit_log_is_itself_audited(client):
    name = unique("it.audit.admin")
    admin = bearer(make_token(name, ["hr_admin"]))
    audit(client, admin)
    rows = audit(client, admin, username=name, action="read").json()["items"]
    assert any(r["resource"] == "audit" for r in rows)


def test_filters_paging_and_order(client, hr):
    name = unique("it.audit.user2")
    user = bearer(make_token(name, ["employee"]))
    for _ in range(3):
        client.get("/departments", headers=user)
    client.get("/employees", params={"q": "simmel"}, headers=user)
    only_search = audit(client, hr, username=name, action="search").json()
    assert only_search["total"] == 1 and only_search["items"][0]["action"] == "search"
    p1 = audit(client, hr, username=name, page_size=2, page=1).json()
    p2 = audit(client, hr, username=name, page_size=2, page=2).json()
    assert p1["total"] == 4 and len(p1["items"]) == 2 and len(p2["items"]) == 2
    ids = [r["id"] for r in p1["items"] + p2["items"]]
    assert ids == sorted(ids, reverse=True) and len(set(ids)) == 4   # newest first, no repeats


def test_page_size_is_capped(client, hr):
    assert audit(client, hr, page_size=201).status_code == 422


def test_denied_requests_are_audited(client, hr):
    name = unique("it.denied")
    user = bearer(make_token(name, ["employee"]))
    assert client.get("/employees/10001/salaries", headers=user).status_code == 403
    assert client.get("/audit", headers=user).status_code == 403
    rows = audit(client, hr, username=name, action="denied").json()["items"]
    assert {r["resource"] for r in rows} == {"employees/10001/salaries", "audit"}
    row = next(r for r in rows if r["resource"] == "audit")
    assert row["role"] == "employee" and row["detail"]["required"] == ["hr_admin"] and row["detail"]["method"] == "GET"


def test_user_without_a_portal_role_is_audited_as_none(client, hr):
    name = unique("it.norole")
    assert client.get("/me", headers=bearer(make_token(name, []))).status_code == 403
    rows = audit(client, hr, username=name).json()["items"]
    assert [(r["action"], r["role"], r["detail"]["reason"]) for r in rows] == [("denied", "none", "no portal role")]
