import base64
import hashlib
import hmac
import json
import os
import time

from fastapi import Depends, Header, HTTPException

from .config import settings

LEVELS = {"viewer": 1, "analyst": 2, "admin": 3}

_SALT_BYTES = 16
_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    salt = os.urandom(_SALT_BYTES)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(dk).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, dk_b64 = stored.split("$", 1)
        salt = base64.urlsafe_b64decode(salt_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
        return hmac.compare_digest(dk, base64.urlsafe_b64decode(dk_b64))
    except Exception:
        return False


def _sign(payload_b64: str) -> str:
    return base64.urlsafe_b64encode(
        hmac.new(settings.auth_secret.encode(), payload_b64.encode(), hashlib.sha256).digest()
    ).decode()


def make_token(username: str, role: str, subsidiary: str, ttl_seconds: int = 12 * 3600) -> str:
    payload = {"sub": username, "role": role, "sub_level": subsidiary, "exp": int(time.time()) + ttl_seconds}
    payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    return payload_b64 + "." + _sign(payload_b64)


def parse_token(token: str) -> dict | None:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        if not hmac.compare_digest(_sign(payload_b64), sig):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_current_user(
    x_api_token: str | None = Header(default=None),
    authorization: str | None = Header(default=None),
):
    from .db import SessionLocal
    from .models import User

    token = x_api_token
    if not token and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()

    payload = parse_token(token) if token else None
    if payload:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == payload["sub"]).first()
        finally:
            db.close()
        return user
    if settings.api_token and (x_api_token == settings.api_token or token == settings.api_token):
        # ponytail: static-token back-compat until all clients move to /auth/login
        return User(username="static", role="admin", subsidiary="", password_hash="")
    return None


def require_min_role(min_role: str):
    def dep(user=Depends(get_current_user)):
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required (login via /auth/login)")
        if LEVELS.get(user.role, 0) < LEVELS.get(min_role, 99):
            raise HTTPException(status_code=403, detail=f"requires {min_role} role")
        return user

    return dep


def scoped_subsidiary(user, requested: str) -> str:
    """Non-admin users are locked to their own subsidiary regardless of the request."""
    if user is not None and user.role != "admin" and user.subsidiary:
        return user.subsidiary
    return requested
