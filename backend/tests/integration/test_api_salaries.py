import pytest
from helpers import bearer, make_token


def salaries(client, headers, emp_no):
    return client.get(f"/employees/{emp_no}/salaries", headers=headers)


def test_employee_role_is_forbidden(client, emp):
    assert salaries(client, emp, 10001).status_code == 403
    assert salaries(client, emp, 10002).status_code == 403   # not even their own


def test_hr_admin_sees_everyone_newest_first(client, hr):
    rows = salaries(client, hr, 10001).json()
    assert [r["salary"] for r in rows] == [88958, 62102, 60117]
    assert len(salaries(client, hr, 10003).json()) == 2
    assert salaries(client, hr, 99999999).status_code == 404


@pytest.mark.parametrize("emp_no,count", [(10001, 3), (10002, 2), (110022, 1), (110039, 2)])
def test_manager_sees_own_department(client, mgr, emp_no, count):
    r = salaries(client, mgr, emp_no)
    assert r.status_code == 200 and len(r.json()) == count


@pytest.mark.parametrize("emp_no", [10003, 10004, 10005, 110114])
def test_manager_cannot_see_other_departments(client, mgr, emp_no):
    # 10005 used to work in Marketing but moved to Finance: past membership must not grant access
    assert salaries(client, mgr, emp_no).status_code == 404


def test_other_departments_manager_sees_only_their_own(client):
    finance_mgr = bearer(make_token("it.dana", ["manager"], emp_no=110114))
    assert salaries(client, finance_mgr, 10003).status_code == 200
    assert salaries(client, finance_mgr, 10005).status_code == 200
    assert salaries(client, finance_mgr, 10001).status_code == 404


def test_former_manager_has_no_access(client):
    ex_mgr = bearer(make_token("it.ex", ["manager"], emp_no=110022))
    assert salaries(client, ex_mgr, 10001).status_code == 404
    assert salaries(client, ex_mgr, 110022).status_code == 404


def test_manager_without_employee_number_fails_closed(client):
    nobody = bearer(make_token("it.nobody", ["manager"]))
    assert salaries(client, nobody, 10001).status_code == 404
