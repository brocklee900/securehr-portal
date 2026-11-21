"""Changing a salary: POST /hr/employees/{n}/salaries and GET /hr/employees/{n}/salary-change (HR admins only).
Needs ADMIN_DATABASE_URL to restore the salary table afterwards (see conftest)."""
import uuid
from datetime import date, timedelta

import pytest
from helpers import bearer, make_token

pytestmark = pytest.mark.usefixtures("salary_restore")

TODAY = date.today()
CURRENT = date(9999, 1, 1)


def change(client, headers, emp_no=10001, salary=95000, effective=TODAY):
    return client.post(f"/hr/employees/{emp_no}/salaries", headers=headers,
                       json={"salary": salary, "effective_date": effective.isoformat()})


def rows(db, emp_no):
    return db.execute("SELECT salary, from_date, to_date FROM hr.salaries WHERE emp_no = %s ORDER BY from_date",
                      (emp_no,)).fetchall()


def test_a_change_today_closes_the_current_salary_and_adds_the_new_one(client, hr, salary_restore):
    before = rows(salary_restore, 10001)
    response = change(client, hr, salary=95000)
    assert response.status_code == 201
    assert response.json()["previous"] == {"salary": 88958, "from_date": "2001-06-22", "to_date": TODAY.isoformat()}
    after = rows(salary_restore, 10001)
    assert after == before[:-1] + [(88958, date(2001, 6, 22), TODAY), (95000, TODAY, CURRENT)]
    history = client.get("/employees/10001/salaries", headers=hr).json()
    assert [(r["salary"], r["to_date"]) for r in history[:2]] == [(95000, "9999-01-01"), (88958, TODAY.isoformat())]


def test_a_managers_salary_can_be_changed_and_their_manager_view_follows(client, hr, mgr, salary_restore):
    assert change(client, hr, emp_no=110039, salary=80000).status_code == 201   # bob, Marketing's manager
    assert [r["salary"] for r in client.get("/employees/10001/salaries", headers=mgr).json()][:1] == [88958]
    assert client.get("/employees/110039/salaries", headers=mgr).json()[0]["salary"] == 80000


def test_a_future_change_is_pending_and_blocks_a_second_one(client, hr, salary_restore):
    later = TODAY + timedelta(days=30)
    assert change(client, hr, salary=97000, effective=later).status_code == 201
    status = client.get("/hr/employees/10001/salary-change", headers=hr).json()
    assert status["can_change"] is False and "already pending" in status["reason"]
    assert status["current"]["salary"] == 88958                     # still in effect until `later`
    assert status["pending"] == {"salary": 97000, "from_date": later.isoformat(), "to_date": "9999-01-01"}
    before = rows(salary_restore, 10001)
    for effective in (TODAY, later + timedelta(days=10)):
        response = change(client, hr, salary=99000, effective=effective)
        assert response.status_code == 409 and "already pending" in response.json()["detail"]
    assert rows(salary_restore, 10001) == before


def test_status_for_an_employee_who_can_be_changed(client, hr):
    status = client.get("/hr/employees/10002/salary-change", headers=hr).json()
    assert status == {"can_change": True, "reason": None,
                      "current": {"salary": 72527, "from_date": "2001-08-02", "to_date": "9999-01-01"},
                      "pending": None, "earliest_date": TODAY.isoformat(),
                      "latest_date": (TODAY + timedelta(days=366)).isoformat()}


def test_another_hr_admins_salary_cannot_be_changed(client, hr, fake_ldap, salary_restore):
    before = rows(salary_restore, 10004)
    response = change(client, hr, emp_no=10004)
    assert response.status_code == 403 and "another HR admin" in response.json()["detail"]
    assert fake_ldap.asked == [10004]
    assert rows(salary_restore, 10004) == before
    status = client.get("/hr/employees/10004/salary-change", headers=hr).json()
    assert status["can_change"] is False and "another HR admin" in status["reason"]


def test_promotion_to_hr_admin_applies_immediately(client, hr, fake_ldap):
    fake_ldap.members.add(10003)
    assert change(client, hr, emp_no=10003, salary=50000).status_code == 403


def test_nobody_can_change_their_own_salary(client, salary_restore):
    me = bearer(make_token("it.hr.self", ["hr_admin"], emp_no=10001))
    before = rows(salary_restore, 10001)
    response = change(client, me)
    assert response.status_code == 403 and "your own salary" in response.json()["detail"]
    assert rows(salary_restore, 10001) == before


def test_ldap_down_means_no_changes(client, hr, fake_ldap, salary_restore):
    fake_ldap.down = True
    before = rows(salary_restore, 10001)
    assert change(client, hr).status_code == 503
    assert client.get("/hr/employees/10001/salary-change", headers=hr).status_code == 503
    assert rows(salary_restore, 10001) == before


@pytest.mark.parametrize("who", ["mgr", "emp"])
def test_only_hr_admin_can_change_or_see_the_form(client, request, salary_restore, who):
    before = rows(salary_restore, 10001)
    assert change(client, request.getfixturevalue(who)).status_code == 403
    assert client.get("/hr/employees/10001/salary-change", headers=request.getfixturevalue(who)).status_code == 403
    assert rows(salary_restore, 10001) == before


def test_changing_needs_a_login(client):
    assert client.post("/hr/employees/10001/salaries", json={"salary": 1, "effective_date": "2030-01-01"}) \
        .status_code == 401


@pytest.mark.parametrize("body,field", [
    ({"salary": 95000, "effective_date": (TODAY - timedelta(days=1)).isoformat()}, "effective_date"),
    ({"salary": 95000, "effective_date": (TODAY + timedelta(days=367)).isoformat()}, "effective_date"),
    ({"salary": 0, "effective_date": TODAY.isoformat()}, "salary"),
    ({"salary": 88958, "effective_date": TODAY.isoformat()}, "salary"),          # same as the current salary
    ({"salary": 95000}, "effective_date"),
    ({"salary": 95000, "effective_date": TODAY.isoformat(), "to_date": "2000-01-01"}, "to_date"),
])
def test_invalid_changes_are_rejected_and_write_nothing(client, hr, salary_restore, body, field):
    before = rows(salary_restore, 10001)
    response = client.post("/hr/employees/10001/salaries", json=body, headers=hr)
    assert response.status_code == 422
    assert field in {err["loc"][-1] for err in response.json()["detail"]}
    assert rows(salary_restore, 10001) == before


def test_unknown_employee_and_employee_without_a_current_salary(client, hr, salary_restore):
    assert change(client, hr, emp_no=99999999).status_code == 404
    assert client.get("/hr/employees/99999999/salary-change", headers=hr).status_code == 404
    salary_restore.execute("UPDATE hr.salaries SET to_date = '2000-01-01' WHERE emp_no = 110022")   # "left"
    assert change(client, hr, emp_no=110022).status_code == 409
    status = client.get("/hr/employees/110022/salary-change", headers=hr).json()
    assert status["can_change"] is False and "no current salary" in status["reason"]


def test_a_salary_that_started_today_can_next_change_tomorrow(client, hr, salary_restore):
    assert change(client, hr, salary=95000).status_code == 201
    response = change(client, hr, salary=96000)
    assert response.status_code == 422 and response.json()["detail"][0]["loc"][-1] == "effective_date"
    assert client.get("/hr/employees/10001/salary-change", headers=hr).json()["earliest_date"] \
        == (TODAY + timedelta(days=1)).isoformat()
    assert change(client, hr, salary=96000, effective=TODAY + timedelta(days=1)).status_code == 201


def test_a_change_is_audited_without_amounts(client, hr):
    name = f"it.hr.{uuid.uuid4().hex[:8]}"
    assert change(client, bearer(make_token(name, ["hr_admin"])), salary=91234).status_code == 201
    (row,) = client.get("/audit", params={"username": name}, headers=hr).json()["items"]
    assert (row["action"], row["resource"], row["role"]) == ("update", "employees/10001/salaries", "hr_admin")
    assert row["detail"] == {"effective_date": TODAY.isoformat()}
    assert "91234" not in str(row) and "88958" not in str(row)


def test_a_refused_hr_admin_target_is_audited(client, hr):
    name = f"it.hr.{uuid.uuid4().hex[:8]}"
    assert change(client, bearer(make_token(name, ["hr_admin"])), emp_no=10004).status_code == 403
    (row,) = client.get("/audit", params={"username": name, "action": "denied"}, headers=hr).json()["items"]
    assert row["resource"] == "employees/10004/salaries"
    assert row["detail"] == {"method": "POST", "reason": "target is an HR admin"}
