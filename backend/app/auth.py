"""OIDC bearer-token validation + role extraction (Keycloak realm roles)."""
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings

ROLE_ORDER = ("hr_admin", "manager", "employee")  # highest privilege first
_bearer = HTTPBearer(auto_error=False)
_jwks = jwt.PyJWKClient(settings.oidc_jwks_url, cache_keys=True)


@dataclass(frozen=True)
class User:
    sub: str
    username: str
    role: str
    emp_no: int | None


def decode_token(token: str) -> dict:
    key = _jwks.get_signing_key_from_jwt(token).key
    return jwt.decode(
        token, key, algorithms=["RS256"],
        audience=settings.oidc_audience, issuer=settings.oidc_issuer,
        options={"require": ["exp", "iss", "aud", "sub"]},
    )


def user_from_claims(claims: dict) -> User:
    roles = claims.get("realm_access", {}).get("roles", [])
    role = next((r for r in ROLE_ORDER if r in roles), None)
    if role is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No portal role assigned")
    emp = claims.get("emp_no")
    return User(claims["sub"], claims.get("preferred_username", claims["sub"]), role,
                int(emp) if emp is not None else None)


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> User:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = decode_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Invalid token: {exc.__class__.__name__}",
                            headers={"WWW-Authenticate": "Bearer"}) from exc
    return user_from_claims(claims)


def require_role(*allowed: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user
    return dep
