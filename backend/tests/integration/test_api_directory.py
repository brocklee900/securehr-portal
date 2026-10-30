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


def test_search_input_is_not_injectable(client, emp):
    r = client.get("/employees", params={"q": "x'); DROP TABLE hr.employees; --"}, headers=emp)
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
