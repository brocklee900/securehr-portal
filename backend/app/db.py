"""Pooled Postgres access. Every request runs in one transaction that carries the caller's
identity into the DB (app.role / app.emp_no) so row-level security can apply, and writes an audit row."""
from contextlib import contextmanager

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from .auth import User
from .config import settings

pool = ConnectionPool(settings.database_url, min_size=1, max_size=10, open=False,
                      kwargs={"row_factory": dict_row})


def write_audit(cur, user: User, action: str, resource: str, detail: dict | None = None) -> None:
    cur.execute("INSERT INTO app.audit_log (username, role, action, resource, detail) "
                "VALUES (%s, %s, %s, %s, %s)",
                (user.username, user.role, action, resource, Jsonb(detail or {})))


@contextmanager
def session(user: User, action: str, resource: str, detail: dict | None = None, *, audit: bool = True):
    """`audit=False` is for writes whose audit row needs something only known mid-request (a new employee's
    number): the caller then calls write_audit() itself, inside the same transaction."""
    with pool.connection() as conn:  # commits on success, rolls back on error
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.role', %s, true), set_config('app.emp_no', %s, true)",
                        (user.role, str(user.emp_no or "")))
            cur.execute("SET LOCAL search_path TO hr, public")
            if audit:
                write_audit(cur, user, action, resource, detail)
            yield cur
