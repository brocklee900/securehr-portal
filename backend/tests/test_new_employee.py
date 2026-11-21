"""Validation rules for creating an employee. Pure model tests: no database, no token."""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import app
from app.routers.hr_admin import HIRE_TITLES, MAX_SALARY, NewEmployee

client = TestClient(app)  # lifespan not started -> no DB needed
TODAY = date.today()


def valid(**overrides):
    return {"first_name": "Ada", "last_name": "Lovelace", "gender": "F", "birth_date": "1990-12-10",
            "hire_date": "2020-01-15", "dept_no": "d001", "title": "Engineer", "salary": 85000, **overrides}


def failed_fields(**overrides):
    """Names of the fields that were rejected (empty set = the request was accepted)."""
    try:
        NewEmployee(**valid(**overrides))
    except ValidationError as caught:
        return {error["loc"][-1] for error in caught.errors()}
    return set()


def test_a_complete_request_is_accepted():
    e = NewEmployee(**valid())
    assert (e.first_name, e.salary, e.hire_date) == ("Ada", 85000, date(2020, 1, 15))


def test_names_are_trimmed():
    e = NewEmployee(**valid(first_name="  Ada ", last_name=" Lovelace  "))
    assert (e.first_name, e.last_name) == ("Ada", "Lovelace")


@pytest.mark.parametrize("first,last", [("Zoë", "O'Brien"), ("Anne-Marie", "de la Cruz"), ("José", "Müller")])
def test_real_world_names_are_accepted(first, last):
    NewEmployee(**valid(first_name=first, last_name=last))


@pytest.mark.parametrize("field,limit", [("first_name", 14), ("last_name", 16)])   # the database column sizes
def test_name_length_limits_match_the_columns(field, limit):
    NewEmployee(**valid(**{field: "x" * limit}))
    assert failed_fields(**{field: "x" * (limit + 1)}) == {field}


@pytest.mark.parametrize("value", ["", "   ", "Ad\na", "Ad\x00a", "Ad\ta", "Ad\u200ba"])
def test_blank_or_control_character_names_are_rejected(value):
    assert failed_fields(first_name=value) == {"first_name"}


@pytest.mark.parametrize("gender", ["X", "m", "", "Male", None])
def test_gender_must_be_M_or_F(gender):
    assert failed_fields(gender=gender) == {"gender"}


@pytest.mark.parametrize("born,ok", [
    ("1900-01-01", True), ("1899-12-31", False), ((TODAY + timedelta(days=1)).isoformat(), False),
])
def test_birth_date_must_be_plausible(born, ok):
    assert ("birth_date" not in failed_fields(birth_date=born)) == ok


@pytest.mark.parametrize("hire,ok", [
    ("2016-02-28", False),   # born on a leap day 2000-02-29: only 15 on 2016-02-28 ...
    ("2016-02-29", True),    # ... and exactly 16 on 2016-02-29
    ("2016-03-01", True),
])
def test_must_be_at_least_16_on_the_hire_date(hire, ok):
    assert failed_fields(birth_date="2000-02-29", hire_date=hire) == (set() if ok else {"hire_date"})


def test_hire_date_may_be_a_year_ahead_but_not_more():
    NewEmployee(**valid(hire_date=(TODAY + timedelta(days=366)).isoformat()))
    assert failed_fields(hire_date=(TODAY + timedelta(days=367)).isoformat()) == {"hire_date"}


@pytest.mark.parametrize("salary,ok", [
    (1, True), (MAX_SALARY, True), (0, False), (-5, False), (MAX_SALARY + 1, False),
    (85000.5, False), ("lots", False), (None, False),
])
def test_salary_must_be_a_sensible_whole_number(salary, ok):
    assert failed_fields(salary=salary) == (set() if ok else {"salary"})


@pytest.mark.parametrize("dept", ["D001", "d01", "d0012", "x001", "d00a", ""])
def test_department_code_format(dept):
    assert failed_fields(dept_no=dept) == {"dept_no"}


@pytest.mark.parametrize("title", HIRE_TITLES)
def test_listed_titles_are_accepted(title):
    NewEmployee(**valid(title=title))


@pytest.mark.parametrize("title", ["Manager", "engineer", "CEO", ""])
def test_other_titles_are_rejected(title):
    assert failed_fields(title=title) == {"title"}


def test_a_client_cannot_choose_the_employee_number_or_other_extras():
    assert failed_fields(emp_no=1) == {"emp_no"}
    assert failed_fields(is_admin=True) == {"is_admin"}


def test_every_field_is_required():
    with pytest.raises(ValidationError) as caught:
        NewEmployee()
    assert {e["loc"][-1] for e in caught.value.errors()} == set(valid())


def test_hr_routes_need_a_login():
    assert client.post("/hr/employees", json=valid()).status_code == 401
    assert client.get("/hr/titles").status_code == 401
