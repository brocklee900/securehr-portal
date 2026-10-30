"""Token minting for integration tests. Tokens are really signed (RS256) and go through the real validation code."""
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from app.config import settings

TEST_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)    # the key the API is told to trust
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)   # an attacker's key


def make_token(username, roles, emp_no=None, key=None, algorithm="RS256", **overrides):
    now = int(time.time())
    claims = {
        "iss": settings.oidc_issuer,
        "aud": settings.oidc_audience,
        "sub": f"sub-{username}",
        "preferred_username": username,
        "iat": now,
        "exp": now + 300,
        "realm_access": {"roles": list(roles) + ["default-roles-securehr", "offline_access"]},
    }
    if emp_no is not None:
        claims["emp_no"] = emp_no
    claims.update(overrides)
    return jwt.encode(claims, TEST_KEY if key is None else key, algorithm=algorithm)


def bearer(token):
    return {"Authorization": f"Bearer {token}"}
