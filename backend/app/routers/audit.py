from fastapi import APIRouter, Depends, Query

from ..auth import User, require_role
from ..db import session

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def audit_log(
    username: str | None = Query(None, max_length=100),
    action: str | None = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_role("hr_admin")),
):
    """HR admins only (API check here, plus a Postgres RLS policy on app.audit_log)."""
    where: list[str] = []
    params: dict = {"limit": page_size, "offset": (page - 1) * page_size}
    if username:
        where.append("username = %(username)s")
        params["username"] = username
    if action:
        where.append("action = %(action)s")
        params["action"] = action
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    # Reading the audit log is itself audited.
    with session(user, "read", "audit", {"username": username, "action": action, "page": page}) as cur:
        cur.execute(
            f"SELECT id, at, username, role, action, resource, detail FROM app.audit_log {clause} "
            "ORDER BY at DESC, id DESC LIMIT %(limit)s OFFSET %(offset)s",
            params,
        )
        items = cur.fetchall()
        cur.execute(f"SELECT count(*) AS n FROM app.audit_log {clause}", params)
        total = cur.fetchone()["n"]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
