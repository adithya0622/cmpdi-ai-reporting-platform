from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text as sqltext

from ..auth import (
    get_current_user,
    hash_password,
    make_token,
    require_min_role,
    verify_password,
)
from ..db import SessionLocal
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    username: str
    password: str


class UserIn(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    subsidiary: str = ""


@router.post("/login")
def login(body: LoginIn):
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == body.username).first()
    finally:
        db.close()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="invalid credentials")
    from ..services.audit import log as audit_log

    audit_log("login", user.username)
    return {
        "token": make_token(user.username, user.role, user.subsidiary),
        "role": user.role,
        "subsidiary": user.subsidiary,
    }


@router.get("/me")
def me(user=Depends(get_current_user)):
    if user is None:
        raise HTTPException(status_code=401, detail="authentication required")
    return {"username": user.username, "role": user.role, "subsidiary": user.subsidiary}


@router.post("/users")
def create_user(body: UserIn, _=Depends(require_min_role("admin"))):
    if body.role not in ("viewer", "analyst", "admin"):
        raise HTTPException(status_code=400, detail="role must be viewer, analyst or admin")
    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == body.username).first():
            raise HTTPException(status_code=409, detail="username already exists")
        db.add(User(username=body.username, password_hash=hash_password(body.password), role=body.role, subsidiary=body.subsidiary))
        db.commit()
        from ..services.audit import log as audit_log

        audit_log("user_create", body.username, {"role": body.role, "subsidiary": body.subsidiary})
        return {"username": body.username, "role": body.role, "status": "created"}
    finally:
        db.close()


@router.get("/users")
def list_users(_user=Depends(require_min_role("admin"))):
    db = SessionLocal()
    try:
        rows = db.execute(
            sqltext("SELECT username, role, subsidiary, created_at FROM users ORDER BY username")
        ).mappings().all()
        return [dict(r) for r in rows]
    finally:
        db.close()
