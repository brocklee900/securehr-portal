from fastapi import APIRouter, Depends

from ..auth import User, require_role
from ..db import session

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def recent_audit(limit: int = 100, user: User = Depends(require_role("hr_admin"))):
    # NOTE: portal_app only has INSERT on audit_log. Grant SELECT to a dedicated reader role (Milestone 7).
    with session(user, "read", "audit") as cur:
        cur.execute("SELECT at, username, role, action, resource, detail FROM app.audit_log ORDER BY at DESC LIMIT %s",
                    (min(limit, 500),))
        return cur.fetchall()
