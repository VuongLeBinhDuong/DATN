"""Minimal demo auth endpoints.

Provides simple login/logout/me flow for UI demo purposes, now with a JSON database for users.
"""

from __future__ import annotations

import base64
import json
import hashlib
import hmac
import os
import time
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/auth", tags=["auth"])

_TOKEN_TTL_SECONDS = 60 * 60 * 8


def _get_users_file_path() -> Path:
    # Ensure data folder exists
    data_dir = Path("data")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "users.json"


def _load_users() -> dict[str, dict]:
    path = _get_users_file_path()
    if not path.is_file():
        # Populate with default admin
        users = {
            "admin": {
                "username": "admin",
                "created_at": int(time.time()),
                "last_active": int(time.time())
            }
        }
        _save_users(users)
        return users
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("users", {})
    except Exception:
        return {}


def _save_users(users: dict[str, dict]) -> None:
    path = _get_users_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"users": users}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


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
        # Verify user in database
        users = _load_users()
        if username not in users:
            # Register user dynamically if token is valid
            users[username] = {
                "username": username,
                "created_at": issued_at,
                "last_active": int(time.time())
            }
        else:
            users[username]["last_active"] = int(time.time())
        _save_users(users)
        return username
    except Exception:
        return None


class LoginIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class RegisterIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=6, max_length=256)


class GuestIn(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)


class AuthOut(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    username: str


class MeOut(BaseModel):
    username: str


class UserRecord(BaseModel):
    username: str
    created_at: int
    last_active: int


class UsersListOut(BaseModel):
    users: list[UserRecord]


@router.post("/login", response_model=AuthOut)
async def login(body: LoginIn) -> AuthOut:
    users = _load_users()
    username = body.username.strip()
    
    # Check admin
    if username == _demo_username() and body.password == _demo_password():
        if username not in users:
            users[username] = {
                "username": username,
                "created_at": int(time.time()),
                "last_active": int(time.time())
            }
        else:
            users[username]["last_active"] = int(time.time())
        _save_users(users)
        token = create_access_token(username)
        return AuthOut(access_token=token, username=username)

    if username not in users:
        raise HTTPException(status_code=401, detail="Tài khoản không tồn tại.")

    user = users[username]
    if "password_hash" in user:
        input_hash = hashlib.sha256(body.password.encode("utf-8")).hexdigest()
        if user["password_hash"] != input_hash:
            raise HTTPException(status_code=401, detail="Mật khẩu không chính xác.")
    else:
        # Legacy auto-created guest account that has no password, let them log in
        pass

    user["last_active"] = int(time.time())
    _save_users(users)
    token = create_access_token(username)
    return AuthOut(access_token=token, username=username)


@router.post("/register", response_model=AuthOut)
async def register(body: RegisterIn) -> AuthOut:
    users = _load_users()
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Tên tài khoản không được trống.")
    
    if username in users:
        raise HTTPException(status_code=400, detail="Tên tài khoản đã tồn tại.")

    password_hash = hashlib.sha256(body.password.encode("utf-8")).hexdigest()
    users[username] = {
        "username": username,
        "password_hash": password_hash,
        "created_at": int(time.time()),
        "last_active": int(time.time())
    }
    _save_users(users)
    token = create_access_token(username)
    return AuthOut(access_token=token, username=username)


@router.post("/register-guest", response_model=AuthOut)
async def register_guest(body: GuestIn) -> AuthOut:
    users = _load_users()
    username = body.username.strip()
    if not username:
        username = f"Khách_{int(time.time()) % 10000:04d}"

    if username not in users:
        users[username] = {
            "username": username,
            "created_at": int(time.time()),
            "last_active": int(time.time())
        }
    else:
        users[username]["last_active"] = int(time.time())

    _save_users(users)
    token = create_access_token(username)
    return AuthOut(access_token=token, username=username)


@router.get("/users", response_model=UsersListOut)
async def list_users() -> UsersListOut:
    users = _load_users()
    sorted_users = sorted(users.values(), key=lambda u: u.get("last_active", 0), reverse=True)
    return UsersListOut(users=[UserRecord(**u) for u in sorted_users])


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
    return {"message": "Đăng xuất thành công."}


