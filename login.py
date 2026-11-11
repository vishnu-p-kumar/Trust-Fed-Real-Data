from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from utils.helpers import load_json, project_paths, save_json

SESSION_COOKIE_NAME = "smartgrid_session"
SESSION_DURATION_HOURS = 12
DEFAULT_USERS = {
    "admin": {
        "email": "admin@gmail.com",
        "role": "admin",
    },
    "inspectors": [],
}


def users_file_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return project_paths().root / "users.json"


def ensure_users_file(path: str | Path | None = None) -> dict[str, Any]:
    target = users_file_path(path)
    if not target.exists():
        save_json(DEFAULT_USERS, target)
    try:
        payload = load_json(target, default=DEFAULT_USERS) or DEFAULT_USERS
    except (json.JSONDecodeError, OSError):
        payload = DEFAULT_USERS
        save_json(payload, target)
    payload.setdefault("admin", DEFAULT_USERS["admin"].copy())
    payload.setdefault("inspectors", [])
    return payload


def _session_secret() -> bytes:
    secret = os.getenv("SMARTGRID_SESSION_SECRET", "").strip()
    if len(secret) < 32:
        raise RuntimeError("SMARTGRID_SESSION_SECRET must be set to at least 32 characters")
    return secret.encode("utf-8")


def hash_password(password: str, *, salt: str | None = None) -> str:
    password_bytes = password.encode("utf-8")
    salt_value = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password_bytes, salt_value.encode("utf-8"), 120_000)
    return f"{salt_value}${digest.hex()}"


def verify_password(password: str, stored_password: str | None = None, stored_hash: str | None = None) -> bool:
    if stored_hash:
        try:
            salt, expected = stored_hash.split("$", 1)
        except ValueError:
            return False
        candidate = hash_password(password, salt=salt).split("$", 1)[1]
        return hmac.compare_digest(candidate, expected)
    if stored_password is None:
        return False
    return hmac.compare_digest(password, stored_password)


def _normalise_inspector(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name") or record.get("username", ""),
        "username": record.get("username", ""),
        "role": "inspector",
        "assigned_area": record.get("assigned_area"),
        "chat_id": record.get("chat_id"),
        "created_at": record.get("created_at"),
    }


def authenticate_user(identifier: str, password: str, path: str | Path | None = None) -> dict[str, Any] | None:
    cleaned_identifier = identifier.strip().lower()
    users = ensure_users_file(path)
    admin = users.get("admin", {})
    admin_email = os.getenv("SMARTGRID_ADMIN_EMAIL", str(admin.get("email", "admin@gmail.com"))).strip().lower()
    admin_password = os.getenv("SMARTGRID_ADMIN_PASSWORD", "")

    if cleaned_identifier == admin_email and admin_password and hmac.compare_digest(password, admin_password):
        return {
            "id": "admin",
            "name": "System Administrator",
            "username": "admin",
            "email": admin_email,
            "role": "admin",
        }

    for inspector in users.get("inspectors", []):
        usernames = {
            str(inspector.get("username", "")).strip().lower(),
            str(inspector.get("email", "")).strip().lower(),
        }
        if cleaned_identifier not in usernames:
            continue
        if verify_password(
            password,
            stored_password=inspector.get("password"),
            stored_hash=inspector.get("password_hash"),
        ):
            normalised = _normalise_inspector(inspector)
            normalised["email"] = str(inspector.get("email", "")).strip().lower() or None
            return normalised
    return None


def redirect_user(user: dict[str, Any]) -> str:
    role_destinations = {
        "admin": "/dashboard/index.html",
        "inspector": "/dashboard/inspector/index.html",
        "client": "/client",
    }
    return role_destinations.get(str(user.get("role") or ""), "/login")


def create_session_token(user: dict[str, Any], *, duration_hours: int = SESSION_DURATION_HOURS) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(hours=duration_hours)
    payload = {
        "sub": user.get("username") or user.get("email") or user.get("id"),
        "name": user.get("name"),
        "role": user.get("role"),
        "assigned_area": user.get("assigned_area"),
        "client_id": user.get("client_id"),
        "organization": user.get("organization"),
        "region": user.get("region"),
        "exp": expires_at.isoformat(),
    }
    body = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("utf-8")
    signature = hmac.new(_session_secret(), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def decode_session_token(token: str | None) -> dict[str, Any] | None:
    if not token or "." not in token:
        return None
    body, signature = token.rsplit(".", 1)
    try:
        secret = _session_secret()
    except RuntimeError:
        return None
    expected_signature = hmac.new(secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None
    try:
        payload = json.loads(base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8"))
    except Exception:
        return None
    try:
        expires_at = datetime.fromisoformat(str(payload.get("exp")))
    except ValueError:
        return None
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        return None
    return {
        "username": payload.get("sub"),
        "name": payload.get("name"),
        "role": payload.get("role"),
        "assigned_area": payload.get("assigned_area"),
        "client_id": payload.get("client_id"),
        "organization": payload.get("organization"),
        "region": payload.get("region"),
        "expires_at": expires_at.isoformat(),
    }
