from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Tenant, User
from ..security import Ctx, create_token, current_ctx, hash_password, require_roles, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])

ROLES = ["admin", "presales", "architect", "finance", "delivery", "viewer"]
DEFAULT_SETTINGS = {"target_margin": 28, "min_margin": 18, "travel_pct": 6, "hide_employee_names": True, "default_confidential": True}


class RegisterIn(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    industry: str = ""
    website: str = ""
    headquarters: str = ""
    name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class InviteIn(BaseModel):
    name: str
    email: EmailStr
    role: str = "presales"
    password: str = Field(min_length=8)


def user_out(u: User, t: Tenant) -> dict:
    return {"id": u.id, "name": u.name, "email": u.email, "role": u.role,
            "tenant": {"id": t.id, "name": t.name, "slug": t.slug, "onboarding": t.onboarding or {}}}


def _slug(db: Session, name: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60] or "company"
    slug, i = base, 1
    while db.scalar(select(func.count()).select_from(Tenant).where(Tenant.slug == slug)):
        i += 1
        slug = f"{base}-{i}"
    return slug


def create_tenant(db: Session, data: RegisterIn) -> tuple[Tenant, User]:
    if db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(409, "An account with this email already exists. Sign in instead.")
    t = Tenant(name=data.company_name.strip(), slug=_slug(db, data.company_name), industry=data.industry, website=data.website,
               headquarters=data.headquarters, settings=dict(DEFAULT_SETTINGS), onboarding={})
    db.add(t)
    db.flush()
    u = User(tenant_id=t.id, email=data.email.lower(), name=data.name.strip(), role="admin", password_hash=hash_password(data.password))
    db.add(u)
    db.commit()
    return t, u


@router.post("/register")
def register(data: RegisterIn, db: Session = Depends(get_db)):
    t, u = create_tenant(db, data)
    return {"token": create_token(u), "user": user_out(u, t)}


@router.post("/login")
def login(data: LoginIn, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(func.lower(User.email) == data.email.lower()))
    if not u or not verify_password(data.password, u.password_hash):
        raise HTTPException(401, "Email or password is incorrect.")
    if not u.is_active:
        raise HTTPException(403, "This account is disabled. Ask your company admin to re-enable it.")
    return {"token": create_token(u), "user": user_out(u, db.get(Tenant, u.tenant_id))}


@router.get("/me")
def me(ctx: Ctx = Depends(current_ctx)):
    return user_out(ctx.user, ctx.tenant)


@router.get("/users")
def list_users(ctx: Ctx = Depends(current_ctx)):
    rows = ctx.db.scalars(select(User).where(User.tenant_id == ctx.tenant_id).order_by(User.created_at)).all()
    return [{"id": u.id, "name": u.name, "email": u.email, "role": u.role, "active": u.is_active} for u in rows]


@router.post("/users")
def invite(data: InviteIn, ctx: Ctx = Depends(require_roles())):
    if data.role not in ROLES:
        raise HTTPException(400, f"Role must be one of: {', '.join(ROLES)}.")
    if ctx.db.scalar(select(User).where(func.lower(User.email) == data.email.lower())):
        raise HTTPException(409, "A user with this email already exists.")
    u = User(tenant_id=ctx.tenant_id, email=data.email.lower(), name=data.name, role=data.role, password_hash=hash_password(data.password))
    ctx.db.add(u)
    ctx.audit("user.invite", data.email, role=data.role)
    ctx.db.commit()
    return {"id": u.id}


@router.patch("/users/{uid}")
def update_user(uid: str, body: dict, ctx: Ctx = Depends(require_roles())):
    u = ctx.db.get(User, uid)
    if not u or u.tenant_id != ctx.tenant_id:
        raise HTTPException(404, "User not found.")
    if "role" in body:
        if body["role"] not in ROLES:
            raise HTTPException(400, "Unknown role.")
        u.role = body["role"]
    if "active" in body:
        if u.id == ctx.user.id:
            raise HTTPException(400, "You can't disable your own account.")
        u.is_active = bool(body["active"])
    ctx.db.commit()
    return {"ok": True}
