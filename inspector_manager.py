from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from login import ensure_users_file, hash_password, users_file_path
from utils.helpers import save_json

USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]{3,32}$")


def _sanitise_inspector(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "name": record.get("name"),
        "username": record.get("username"),
        "assigned_area": record.get("assigned_area"),
        "chat_id": record.get("chat_id"),
        "role": record.get("role", "inspector"),
        "created_at": record.get("created_at"),
    }


def create_inspector(
    name: str,
    username: str,
    password: str,
    assigned_area: str,
    chat_id: str,
    path: str | Path | None = None,
) -> dict[str, Any]:
    clean_name = name.strip()
    clean_username = username.strip().lower()
    clean_password = password.strip()
    clean_area = assigned_area.strip()
    clean_chat_id = chat_id.strip()
    if len(clean_name) < 3:
        raise ValueError("Inspector name must be at least 3 characters long.")
    if not USERNAME_PATTERN.match(clean_username):
        raise ValueError("Username must be 3-32 characters and use letters, numbers, dot, underscore, or hyphen.")
    if len(clean_password) < 6:
        raise ValueError("Password must be at least 6 characters long.")
    if len(clean_area) < 2:
        raise ValueError("Assigned inspection area is required.")
    if not re.fullmatch(r"-?\d{6,20}", clean_chat_id):
        raise ValueError("Telegram chat ID must be a valid numeric chat ID.")

    payload = ensure_users_file(path)
    existing = {
        str(item.get("username", "")).strip().lower()
        for item in payload.get("inspectors", [])
    }
    if clean_username in existing:
        raise ValueError("Inspector username already exists.")

    record = {
        "id": f"ins-{uuid.uuid4().hex[:10]}",
        "name": clean_name,
        "username": clean_username,
        "assigned_area": clean_area,
        "chat_id": clean_chat_id,
        "password_hash": hash_password(clean_password),
        "role": "inspector",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.setdefault("inspectors", []).append(record)
    save_json(payload, users_file_path(path))
    return _sanitise_inspector(record)


def get_all_inspectors(path: str | Path | None = None) -> list[dict[str, Any]]:
    payload = ensure_users_file(path)
    inspectors = [_sanitise_inspector(item) for item in payload.get("inspectors", [])]
    return sorted(inspectors, key=lambda item: (item.get("name") or "", item.get("username") or ""))


def delete_inspector(username: str, path: str | Path | None = None) -> bool:
    payload = ensure_users_file(path)
    target_username = username.strip().lower()
    inspectors = payload.get("inspectors", [])
    filtered = [item for item in inspectors if str(item.get("username", "")).strip().lower() != target_username]
    if len(filtered) == len(inspectors):
        return False
    payload["inspectors"] = filtered
    save_json(payload, users_file_path(path))
    return True
