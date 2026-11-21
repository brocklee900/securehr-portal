"""Salary-change rules that need no database: the request model, who may be changed, and the LDAP lookup."""
from datetime import date, timedelta

import pytest
from fastapi import HTTPException
from ldap3 import MOCK_SYNC, OFFLINE_SLAPD_2_4, Connection, Server
from ldap3.core.exceptions import LDAPSocketOpenError
from pydantic import ValidationError

from app import hr_lookup
from app.auth import User
from app.routers import hr_admin
from app.routers.hr_admin import MAX_SALARY, SalaryChange

TODAY = date.today()
HR = User("sub-alice", "alice.hr", "hr_admin", None)


def rejected(**body):
    try:
        SalaryChange(**{"salary": 90000, "effective_date": TODAY, **body})
    except ValidationError as caught:
        return {error["loc"][-1] for error in caught.errors()}
    return set()


@pytest.mark.parametrize("days,ok", [(-1, False), (0, True), (366, True), (367, False)])
def test_effective_date_is_today_up_to_a_year_ahead(days, ok):
    assert rejected(effective_date=TODAY + timedelta(days=days)) == (set() if ok else {"effective_date"})


@pytest.mark.parametrize("salary,ok", [(1, True), (MAX_SALARY, True), (0, False), (MAX_SALARY + 1, False),
                                       (9.5, False), ("x", False)])
def test_salary_limits(salary, ok):
    assert rejected(salary=salary) == (set() if ok else {"salary"})


def test_unknown_fields_are_rejected():
    assert rejected(to_date="2000-01-01") == {"to_date"}


def test_own_salary_is_blocked_without_asking_ldap(monkeypatch):
    monkeypatch.setattr(hr_admin, "is_hr_admin", lambda n: pytest.fail("LDAP should not be asked"))
    assert hr_admin._who_blocks(User("s", "hr.self", "hr_admin", 10001), 10001) == "own salary"


@pytest.mark.parametrize("in_group,expected", [(True, "target is an HR admin"), (False, None)])
def test_hr_admin_targets_are_blocked(monkeypatch, in_group, expected):
    monkeypatch.setattr(hr_admin, "is_hr_admin", lambda n: in_group)
    assert hr_admin._who_blocks(HR, 10004) == expected


def test_ldap_trouble_refuses_with_503(monkeypatch):
    def down(_):
        raise hr_lookup.HrLookupUnavailable("down")
    monkeypatch.setattr(hr_admin, "is_hr_admin", down)
    with pytest.raises(HTTPException) as caught:
        hr_admin._who_blocks(HR, 10004)
    assert caught.value.status_code == 503


# ---------- the LDAP lookup itself, against ldap3's in-memory directory ----------
PEOPLE = "ou=people,dc=securehr,dc=local"
BIND = "cn=readonly,dc=securehr,dc=local"


@pytest.fixture
def directory(monkeypatch):
    monkeypatch.setattr(hr_lookup.settings, "ldap_bind_password", "pw")
    server = Server("fake", get_info=OFFLINE_SLAPD_2_4)
    conn = Connection(server, user=BIND, password="pw", client_strategy=MOCK_SYNC)
    add = conn.strategy.add_entry
    add(BIND, {"objectClass": "simpleSecurityObject", "userPassword": "pw"})
    add(f"uid=alice.hr,{PEOPLE}", {"objectClass": "inetOrgPerson", "uid": "alice.hr", "employeeNumber": "10004"})
    add(f"uid=bob.manager,{PEOPLE}", {"objectClass": "inetOrgPerson", "uid": "bob.manager",
                                       "employeeNumber": "110039"})
    add(f"uid=dup.hr,{PEOPLE}", {"objectClass": "inetOrgPerson", "uid": "dup.hr", "employeeNumber": "10003"})
    add(f"uid=dup.plain,{PEOPLE}", {"objectClass": "inetOrgPerson", "uid": "dup.plain", "employeeNumber": "10003"})
    add("cn=hr-admins,ou=groups,dc=securehr,dc=local",
        {"objectClass": "groupOfNames", "cn": "hr-admins", "member": [f"uid=alice.hr,{PEOPLE}", f"uid=dup.hr,{PEOPLE}"]})
    add("cn=managers,ou=groups,dc=securehr,dc=local",
        {"objectClass": "groupOfNames", "cn": "managers", "member": [f"uid=bob.manager,{PEOPLE}"]})
    return lambda: conn


@pytest.mark.parametrize("emp_no,expected", [
    (10004, True),      # alice is in hr-admins
    (110039, False),    # bob is only a manager
    (10001, False),     # nobody in LDAP has this number
    (10003, True),      # two people share the number; one is HR: treat as HR (the safe answer)
])
def test_lookup_answers_from_the_directory(directory, emp_no, expected):
    assert hr_lookup.is_hr_admin(emp_no, connect=directory) is expected


def test_lookup_fails_closed_when_ldap_cannot_be_reached():
    def unreachable():
        raise LDAPSocketOpenError("no route")
    with pytest.raises(hr_lookup.HrLookupUnavailable):
        hr_lookup.is_hr_admin(10004, connect=unreachable)


def test_lookup_fails_closed_without_a_configured_password(monkeypatch):
    monkeypatch.setattr(hr_lookup.settings, "ldap_bind_password", "")
    with pytest.raises(hr_lookup.HrLookupUnavailable):
        hr_lookup.is_hr_admin(10004)


def test_lookup_fails_closed_on_a_wrong_password(directory, monkeypatch):
    conn = directory()
    conn.password = "wrong"
    with pytest.raises(hr_lookup.HrLookupUnavailable):
        hr_lookup.is_hr_admin(10004, connect=lambda: conn)
