"""Creating an employee: POST /hr/employees (HR admins only). Needs ADMIN_DATABASE_URL to clean up (see conftest)."""
import uuid
from datetime import date

import psycopg
import pytest
from helpers import bearer, make_token

pytestmark = pytest.mark.usefixtures("hire_cleanup")

TODAY = date.today()
CURRENT = date(9999, 1, 1)
TABLES = ("employees", "dept_emp", "titles", "salaries")


def payload(**overrides):
    body = {"first_name": "Ada", "last_name": "Lovelace", "gender": "F", "birth_date": "1990-12-10",
            "hire_date": TODAY.isoformat(), "dept_no": "d001", "title": "Engineer", "salary": 85000}
    body.update(overrides)
    return body


def create(client, headers, **overrides):
    return client.post("/hr/employees", json=payload(**overrides), headers=headers)


def count(conn, table):
    return conn.execute(f"SELECT count(*) FROM hr.{table}").fetchone()[0]


def counts(conn):
    return {t: count(conn, t) for t in TABLES}


def test_hr_admin_creates_the_employee_in_all_four_tables(client, hr, hire_cleanup):
    response = create(client, hr)
    assert response.status_code == 201
    body = response.json()
    n = body["emp_no"]
    assert n > 110114 and body["dept_name"] == "Marketing"
    assert {k: body[k] for k in ("first_name", "last_name", "gender", "dept_no", "title", "salary")} == {
        "first_name": "Ada", "last_name": "Lovelace", "gender": "F", "dept_no": "d001", "title": "Engineer",
        "salary": 85000}
    db = hire_cleanup
    assert db.execute("SELECT birth_date, first_name, last_name, gender, hire_date FROM hr.employees "
                      "WHERE emp_no = %s", (n,)).fetchall() == [(date(1990, 12, 10), "Ada", "Lovelace", "F", TODAY)]
    # start dates are the hire date; end dates are the dataset's "current" marker
    assert db.execute("SELECT dept_no, from_date, to_date FROM hr.dept_emp WHERE emp_no = %s", (n,)).fetchall() \
        == [("d001", TODAY, CURRENT)]
    assert db.execute("SELECT title, from_date, to_date FROM hr.titles WHERE emp_no = %s", (n,)).fetchall() \
        == [("Engineer", TODAY, CURRENT)]
    assert db.execute("SELECT salary, from_date, to_date FROM hr.salaries WHERE emp_no = %s", (n,)).fetchall() \
        == [(85000, TODAY, CURRENT)]


def test_the_new_employee_appears_wherever_the_directory_looks(client, hr, emp):
    n = create(client, hr).json()["emp_no"]
    detail = client.get(f"/employees/{n}", headers=hr).json()
    assert (detail["first_name"], detail["last_name"], detail["dept_name"], detail["title"], detail["gender"]) \
        == ("Ada", "Lovelace", "Marketing", "Engineer", "F")
    assert detail["birth_date"] == "1990-12-10" and detail["hire_date"] == TODAY.isoformat()
    assert [r["emp_no"] for r in client.get("/employees", params={"q": "lovelace"}, headers=emp).json()["items"]] == [n]
    in_marketing = client.get("/employees", params={"dept_no": "d001", "page_size": 100}, headers=emp).json()["items"]
    assert n in {r["emp_no"] for r in in_marketing}
    assert [t["title"] for t in client.get(f"/employees/{n}/titles", headers=hr).json()] == ["Engineer"]
    assert [s["salary"] for s in client.get(f"/employees/{n}/salaries", headers=hr).json()] == [85000]
    headcount = {d["dept_no"]: d["headcount"] for d in client.get("/departments", headers=hr).json()}
    assert headcount["d001"] == 5      # the four seeded people plus Ada


def test_employee_numbers_are_unique_and_increasing(client, hr):
    first = create(client, hr).json()["emp_no"]
    second = create(client, hr, first_name="Grace", last_name="Hopper").json()["emp_no"]
    assert second > first


def test_hiring_invalidates_cached_directory_counts_for_all_users(client, hr, emp):
    searches = [
        (emp, {}),
        (hr, {}),
        (emp, {"dept_no": "d001"}),
        (emp, {"q": "lovelace", "title": "engineer", "hired_from": TODAY.isoformat(),
               "hired_to": TODAY.isoformat()}),
    ]
    before = [client.get("/employees", headers=user, params=params).json()["total"]
              for user, params in searches]
    assert before == [8, 8, 4, 0]
    assert create(client, hr).status_code == 201
    for (user, params), total in zip(searches, before):
        response = client.get("/employees", headers=user, params={**params, "sort_by": "hire_date"})
        assert response.status_code == 200
        assert response.json()["total"] == total + 1


def test_a_manager_sees_a_new_hires_salary_only_in_their_own_department(client, hr, mgr):
    marketing = create(client, hr, dept_no="d001").json()["emp_no"]
    finance = create(client, hr, dept_no="d002", first_name="Grace").json()["emp_no"]
    assert client.get(f"/employees/{marketing}/salaries", headers=mgr).status_code == 200
    assert client.get(f"/employees/{finance}/salaries", headers=mgr).status_code == 404


@pytest.mark.parametrize("who", ["mgr", "emp"])
def test_only_hr_admin_can_create(client, request, hire_cleanup, who):
    before = counts(hire_cleanup)
    assert create(client, request.getfixturevalue(who)).status_code == 403
    assert counts(hire_cleanup) == before


def test_creating_needs_a_login(client, hire_cleanup):
    before = counts(hire_cleanup)
    assert client.post("/hr/employees", json=payload()).status_code == 401
    assert client.get("/hr/titles").status_code == 401
    assert counts(hire_cleanup) == before


def test_a_refused_creation_attempt_is_audited(client, hr):
    name = f"it.sneaky.{uuid.uuid4().hex[:8]}"
    assert create(client, bearer(make_token(name, ["manager"], emp_no=110039))).status_code == 403
    rows = client.get("/audit", params={"username": name, "action": "denied"}, headers=hr).json()["items"]
    assert [(r["resource"], r["detail"]["method"], r["detail"]["required"]) for r in rows] \
        == [("hr/employees", "POST", ["hr_admin"])]


def test_hr_titles_are_for_hr_admins_and_exclude_manager(client, hr, mgr, emp):
    titles = client.get("/hr/titles", headers=hr).json()
    assert "Engineer" in titles and "Manager" not in titles
    assert client.get("/hr/titles", headers=mgr).status_code == 403
    assert client.get("/hr/titles", headers=emp).status_code == 403


def test_creation_is_audited_without_personal_data(client, hr):
    name = f"it.hr.{uuid.uuid4().hex[:8]}"
    me = bearer(make_token(name, ["hr_admin"]))
    n = create(client, me, salary=91234).json()["emp_no"]
    rows = client.get("/audit", params={"username": name}, headers=hr).json()["items"]
    (row,) = rows                      # exactly one entry: no duplicate "request" row
    assert (row["action"], row["resource"], row["role"]) == ("create", f"employees/{n}", "hr_admin")
    assert row["detail"] == {"dept_no": "d001", "title": "Engineer"}
    assert not {"Ada", "Lovelace", "91234", "1990-12-10"} & set(str(row).replace(",", " ").replace("'", " ").split())


@pytest.mark.parametrize("overrides,field", [
    ({"dept_no": "d999"}, "dept_no"),                    # well-formed but not a department (checked in the database)
    ({"title": "Manager"}, "title"),
    ({"salary": 0}, "salary"),
    ({"gender": "X"}, "gender"),
    ({"first_name": "A" * 15}, "first_name"),
    ({"birth_date": "2999-01-01"}, "birth_date"),
    ({"hire_date": "2000-01-01"}, "hire_date"),          # employee would be 9 years old
    ({"emp_no": 5}, "emp_no"),                           # clients cannot choose the number
])
def test_invalid_requests_are_rejected_and_write_nothing(client, hr, hire_cleanup, overrides, field):
    before = counts(hire_cleanup)
    response = create(client, hr, **overrides)
    assert response.status_code == 422
    assert field in {err["loc"][-1] for err in response.json()["detail"]}
    assert counts(hire_cleanup) == before


def test_missing_fields_are_rejected(client, hr):
    body = payload()
    del body["salary"], body["dept_no"]
    response = client.post("/hr/employees", json=body, headers=hr)
    assert response.status_code == 422
    assert {err["loc"][-1] for err in response.json()["detail"]} == {"salary", "dept_no"}


def test_a_failure_part_way_leaves_nothing_behind(client, hr, hire_cleanup):
    """All four inserts are one transaction. Force the LAST one (salaries) to fail and check the first three vanish."""
    db = hire_cleanup
    before = counts(db)
    db.execute("ALTER TABLE hr.salaries ADD CONSTRAINT it_refuse_77777 CHECK (salary <> 77777)")
    try:
        with pytest.raises(psycopg.errors.CheckViolation):
            create(client, hr, salary=77777)
    finally:
        db.execute("ALTER TABLE hr.salaries DROP CONSTRAINT it_refuse_77777")
    assert counts(db) == before


def test_a_stale_numbering_sequence_is_reported_clearly(client, hr, hire_cleanup):
    db = hire_cleanup
    top = db.execute("SELECT max(emp_no) FROM hr.employees").fetchone()[0]
    db.execute("SELECT setval('hr.employees_emp_no_seq', 10001)")      # next number, 10002, belongs to Simmel
    try:
        response = create(client, hr)
    finally:
        db.execute("SELECT setval('hr.employees_emp_no_seq', %s)", (top,))
    assert response.status_code == 409 and "04_hr_write_access.sql" in response.json()["detail"]
    assert create(client, hr).status_code == 201                       # and it recovers once the sequence is right
