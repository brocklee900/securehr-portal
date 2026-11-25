"""Count reuse, expiration, isolation and invalidation without a database."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import employee_counts
from app.auth import User, current_user
from app.employee_counts import EmployeeCountCache
from app.routers import employees


@pytest.fixture
def search_client(monkeypatch):
    state = SimpleNamespace(total=8, counts=0, reads=0, audits=[], fail_commit=False,
                            user=User("1", "carol", "employee", 10002))
    monkeypatch.setattr(employees, "employee_count_cache", EmployeeCountCache())

    class Cursor:
        def execute(self, sql, params):
            if sql.startswith("SELECT count(*)"):
                state.counts += 1
            else:
                state.reads += 1

        def fetchall(self):
            return []

        def fetchone(self):
            return {"n": state.total}

    @contextmanager
    def session(user, action, resource, detail):
        state.audits.append((user, action, resource, detail))
        yield Cursor()
        if state.fail_commit:
            raise RuntimeError("commit failed")

    monkeypatch.setattr(employees, "session", session)
    app = FastAPI()
    app.include_router(employees.router)
    app.dependency_overrides[current_user] = lambda: state.user
    with TestClient(app) as client:
        yield client, state


def test_paging_and_sorting_reuse_count_but_still_read_and_audit(search_client):
    client, state = search_client
    for params in ({}, {"page": 2}, {"page_size": 50, "sort_by": "title", "sort_dir": "desc"}):
        response = client.get("/employees", params=params)
        assert response.status_code == 200
        assert response.json()["total"] == 8
    assert state.counts == 1
    assert state.reads == 3
    assert [(action, resource) for _, action, resource, _ in state.audits] == [("search", "employees")] * 3


@pytest.mark.parametrize("filters", [
    {"q": "ada"}, {"dept_no": "d001"}, {"title": "engineer"},
    {"hired_from": "1986-01-01"}, {"hired_to": "1989-12-31"},
])
def test_each_filter_gets_its_own_total(search_client, filters):
    client, state = search_client
    assert client.get("/employees").json()["total"] == 8
    state.total = 3
    assert client.get("/employees", params=filters).json()["total"] == 3
    assert client.get("/employees", params={**filters, "page": 2}).json()["total"] == 3
    assert client.get("/employees").json()["total"] == 8
    assert state.counts == 2


def test_case_insensitive_filters_share_cached_zero_counts(search_client):
    client, state = search_client
    state.total = 0
    for filters in ({"q": "ADA", "title": "ENGINEER"}, {"q": "ada", "title": "engineer"}):
        assert client.get("/employees", params=filters).json()["total"] == 0
    assert state.counts == 1


@pytest.mark.parametrize("user", [
    User("2", "other", "employee", 10002),
    User("1", "carol", "manager", 10002),
    User("1", "carol", "employee", 10003),
])
def test_totals_are_isolated_by_user_and_visibility(search_client, user):
    client, state = search_client
    assert client.get("/employees").json()["total"] == 8
    state.user, state.total = user, 4
    assert client.get("/employees").json()["total"] == 4
    assert state.counts == 2


def test_expiration_recounts_even_when_pages_keep_being_requested(search_client, monkeypatch):
    client, state = search_client
    clock = SimpleNamespace(now=100.0)
    monkeypatch.setattr(employee_counts, "monotonic", lambda: clock.now)
    assert client.get("/employees").json()["total"] == 8
    clock.now = 159.0
    state.total = 9
    assert client.get("/employees", params={"page": 2}).json()["total"] == 8
    clock.now = 160.0
    assert client.get("/employees", params={"page": 3}).json()["total"] == 9
    assert state.counts == 2


def test_failed_transactions_do_not_cache_the_count(search_client):
    client, state = search_client
    state.fail_commit = True
    with pytest.raises(RuntimeError, match="commit failed"):
        client.get("/employees")
    state.fail_commit, state.total = False, 9
    assert client.get("/employees").json()["total"] == 9
    assert state.counts == 2


def test_invalidation_prevents_in_flight_counts_from_being_cached():
    cache = EmployeeCountCache()
    _, generation = cache.get("all")
    cache.put("filtered", 3, generation)
    cache.invalidate()
    cache.put("all", 8, generation)  # A search that began before the hire finished later.
    assert cache.get("all")[0] is None
    assert cache.get("filtered")[0] is None
    _, fresh_generation = cache.get("all")
    cache.put("all", 9, fresh_generation)
    assert cache.get("all")[0] == 9


def test_cache_evicts_least_recently_used_counts_at_capacity():
    cache = EmployeeCountCache(max_entries=2)
    _, generation = cache.get("first")
    cache.put("first", 1, generation)
    cache.put("second", 2, generation)
    assert cache.get("first")[0] == 1
    cache.put("third", 3, generation)
    assert cache.get("second")[0] is None
    assert cache.get("first")[0] == 1
    assert cache.get("third")[0] == 3
