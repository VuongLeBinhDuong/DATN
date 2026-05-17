"""Minimal demo auth endpoints.

Provides simple login/logout/me flow for UI demo purposes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])

_TOKEN_TTL_SECONDS = 60 * 60 * 8


def _auth_secret() -> str:
    return os.getenv("DATN_AUTH_SECRET", "datn-demo-secret")


def _demo_username() -> str:
    return os.getenv("DATN_DEMO_USER", "admin")


def _demo_password() -> str:
    return os.getenv("DATN_DEMO_PASS", "admin123")


def _sign(payload: str) -> str:
    digest = hmac.new(_auth_secret().encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return digest


def create_access_token(username: str) -> str:
    issued_at = int(time.time())
    payload = f"{username}:{issued_at}"
    signature = _sign(payload)
    raw = f"{payload}:{signature}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("utf-8")


def verify_access_token(token: str) -> str | None:
    try:
        raw = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        username, issued_raw, signature = raw.rsplit(":", 2)
        payload = f"{username}:{issued_raw}"
        if not hmac.compare_digest(_sign(payload), signature):
            return None
        issued_at = int(issued_raw)
        if int(time.time()) - issued_at > _TOKEN_TTL_SECONDS:
            return None
        return username
    except Exception:
        return None


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    username: str


class MeOut(BaseModel):
    username: str


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn) -> AuthOut:
    if body.username != _demo_username() or body.password != _demo_password():
        raise HTTPException(status_code=401, detail="Sai tài khoản hoặc mật khẩu.")
    token = create_access_token(body.username)
    return AuthOut(access_token=token, username=body.username)


@router.get("/me", response_model=MeOut)
async def me(authorization: str = Header(default="")) -> MeOut:
    prefix = "Bearer "
    token = authorization[len(prefix) :] if authorization.startswith(prefix) else ""
    username = verify_access_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Phiên đăng nhập không hợp lệ hoặc đã hết hạn.")
    return MeOut(username=username)


@router.post("/logout")
async def logout() -> dict[str, str]:
    # Stateless token demo: frontend removes token.
    return {"message": "Đăng xuất thành công."}
