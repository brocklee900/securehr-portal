import pytest


def last_names(items):
    return [i["last_name"] for i in items]


def test_search_by_name_returns_current_department_and_title(client, emp):
    body = client.get("/employees", params={"q": "koblick"}, headers=emp).json()
    assert body["total"] == 1
    row = body["items"][0]
    assert (row["emp_no"], row["dept_name"], row["title"]) == (10004, "Finance", "Engineer")


def test_search_is_case_insensitive_and_matches_full_name(client, emp):
    assert last_names(client.get("/employees", params={"q": "GEORGI"}, headers=emp).json()["items"]) == ["Facello"]
    assert last_names(client.get("/employees", params={"q": "georgi fac"}, headers=emp).json()["items"]) == ["Facello"]


def test_search_with_no_match_is_empty(client, emp):
    body = client.get("/employees", params={"q": "zzzz"}, headers=emp).json()
    assert body["total"] == 0 and body["items"] == []


def test_search_needs_two_characters(client, emp):
    assert client.get("/employees", params={"q": "g"}, headers=emp).status_code == 422


def test_page_size_is_capped(client, emp):
    assert client.get("/employees", params={"page_size": 101}, headers=emp).status_code == 422


def test_pagination_is_ordered_and_complete(client, emp):
    def page(n):
        return client.get("/employees", params={"page": n, "page_size": 3}, headers=emp).json()
    p1, p2, p3 = page(1), page(2), page(3)
    assert p1["total"] == 8
    assert last_names(p1["items"]) == ["Bamford", "Facello", "Koblick"]
    assert last_names(p2["items"]) == ["Legleitner", "Maliniak", "Markovitch"]
    assert last_names(p3["items"]) == ["Minakawa", "Simmel"]


def test_department_filter_uses_current_department_only(client, emp):
    d1 = client.get("/employees", params={"dept_no": "d001"}, headers=emp).json()
    d2 = client.get("/employees", params={"dept_no": "d002"}, headers=emp).json()
    assert set(last_names(d1["items"])) == {"Facello", "Simmel", "Markovitch", "Minakawa"}
    assert set(last_names(d2["items"])) == {"Bamford", "Koblick", "Maliniak", "Legleitner"}   # Maliniak moved d001 -> d002


@pytest.mark.parametrize("title,expected", [
    ("eNgIn", ["Bamford", "Koblick", "Maliniak"]),
    ("Senior Engineer", ["Bamford", "Maliniak"]),
    ("zzzz", []),
])
def test_title_filter_matches_current_title_substrings(client, emp, title, expected):
    response = client.get("/employees", params={"title": title}, headers=emp)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(expected)
    assert last_names(body["items"]) == expected  # Facello's former Engineer title must not match.


@pytest.mark.parametrize("dates,expected", [
    ({"hired_from": "1986-06-26", "hired_to": "1986-12-01"}, ["Bamford", "Facello", "Koblick"]),
    ({"hired_from": "1986-12-01"}, ["Koblick", "Maliniak"]),
    ({"hired_to": "1985-01-14"}, ["Legleitner", "Markovitch"]),
    ({"hired_from": "1986-06-26", "hired_to": "1986-06-26"}, ["Facello"]),
    ({"hired_from": "2000-01-01", "hired_to": "2001-01-01"}, []),
])
def test_hire_date_filter_is_inclusive_and_allows_open_ends(client, emp, dates, expected):
    response = client.get("/employees", params=dates, headers=emp)
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == len(expected)
    assert last_names(body["items"]) == expected


@pytest.mark.parametrize("dates", [
    {"hired_from": "not-a-date"},
    {"hired_to": "1986-02-30"},
    {"hired_from": "1987-01-01", "hired_to": "1986-01-01"},
])
def test_invalid_hire_date_ranges_are_rejected(client, emp, dates):
    assert client.get("/employees", params=dates, headers=emp).status_code == 422


def test_all_filters_combine_with_sorting_and_pagination(client, emp):
    employees = []
    for page in (1, 2, 3):
        response = client.get("/employees", headers=emp, params={
            "q": "li", "dept_no": "d002", "title": "engineer",
            "hired_from": "1986-12-01", "hired_to": "1989-09-12",
            "sort_by": "hire_date", "sort_dir": "desc", "page_size": 1, "page": page,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert len(body["items"]) == (1 if page <= 2 else 0)
        employees.extend(row["emp_no"] for row in body["items"])
    assert employees == [10005, 10004]


@pytest.mark.parametrize("sort_by,ascending", [
    ("name", [10003, 10001, 10004, 110114, 10005, 110022, 110039, 10002]),
    ("title", [10004, 110114, 110022, 110039, 10003, 10005, 10001, 10002]),
    ("department", [10003, 10004, 110114, 10005, 10001, 110022, 110039, 10002]),
    ("hire_date", [110022, 110114, 10002, 110039, 10001, 10003, 10004, 10005]),
])
@pytest.mark.parametrize("sort_dir", ["asc", "desc"])
def test_sorting_applies_to_all_pages(client, emp, sort_by, ascending, sort_dir):
    employees = []
    for page in (1, 2, 3):
        response = client.get("/employees", headers=emp, params={
            "sort_by": sort_by, "sort_dir": sort_dir, "page_size": 3, "page": page,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 8
        employees.extend(row["emp_no"] for row in body["items"])
    assert employees == (ascending if sort_dir == "asc" else ascending[::-1])


def test_sorting_preserves_search_and_department_filters(client, emp):
    employees = []
    for page in (1, 2):
        response = client.get("/employees", headers=emp, params={
            "q": "li", "dept_no": "d002", "sort_by": "hire_date", "sort_dir": "desc",
            "page_size": 1, "page": page,
        })
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        employees.extend(row["emp_no"] for row in body["items"])
    assert employees == [10005, 10004]


@pytest.mark.parametrize("params", [
    {"sort_by": "salary"},
    {"sort_by": "name; DROP TABLE hr.employees; --"},
    {"sort_dir": "sideways"},
    {"sort_dir": "desc; DROP TABLE hr.employees; --"},
])
def test_sorting_rejects_unsupported_values(client, emp, params):
    assert client.get("/employees", headers=emp, params=params).status_code == 422


@pytest.mark.parametrize("field", ["q", "title"])
def test_search_input_is_not_injectable(client, emp, field):
    r = client.get("/employees", params={field: "x'); DROP TABLE hr.employees; --"}, headers=emp)
    assert r.status_code == 200 and r.json()["total"] == 0
    assert client.get("/employees", params={"q": "koblick"}, headers=emp).json()["total"] == 1


def test_employee_role_gets_basic_directory_fields_only(client, emp):
    body = client.get("/employees/10001", headers=emp).json()
    assert (body["first_name"], body["dept_name"], body["title"]) == ("Georgi", "Marketing", "Staff")
    assert "birth_date" not in body and "gender" not in body


def test_manager_and_hr_get_demographics(client, mgr, hr):
    for headers in (mgr, hr):
        body = client.get("/employees/10001", headers=headers).json()
        assert body["gender"] == "M" and body["birth_date"] == "1953-09-02"


def test_unknown_employee_is_404(client, emp):
    assert client.get("/employees/99999999", headers=emp).status_code == 404


def test_title_history_is_newest_first(client, emp):
    titles = client.get("/employees/10001/titles", headers=emp).json()
    assert [t["title"] for t in titles] == ["Staff", "Senior Engineer"]


def test_department_list_counts_current_headcount(client, emp):
    depts = {d["dept_no"]: d for d in client.get("/departments", headers=emp).json()}
    assert depts["d001"]["headcount"] == 4 and depts["d002"]["headcount"] == 4
    assert depts["d003"]["headcount"] == 0 and depts["d001"]["dept_name"] == "Marketing"


def test_department_detail_lists_current_and_former_managers(client, emp):
    body = client.get("/departments/d001", headers=emp).json()
    assert [m["emp_no"] for m in body["managers"]] == [110039, 110022]   # newest first
    assert client.get("/departments/d999", headers=emp).status_code == 404


def test_department_employees(client, emp):
    rows = client.get("/departments/d002/employees", headers=emp).json()
    assert {r["last_name"] for r in rows} == {"Bamford", "Koblick", "Maliniak", "Legleitner"}
