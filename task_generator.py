from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

import pandas as pd

from utils.helpers import load_json, project_paths, save_json, to_builtin

DEFAULT_TASK_STORE = {"tasks": []}


def tasks_file_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    return project_paths().root / "inspection_tasks.json"


def ensure_tasks_file(path: str | Path | None = None) -> dict[str, Any]:
    target = tasks_file_path(path)
    if not target.exists():
        save_json(DEFAULT_TASK_STORE, target)
    payload = load_json(target, default=DEFAULT_TASK_STORE) or DEFAULT_TASK_STORE
    payload.setdefault("tasks", [])
    return payload


def risk_from_anomaly_score(anomaly_score: Any) -> str:
    score = float(anomaly_score or 0.0)
    if score > 0.9:
        return "HIGH"
    if score >= 0.7:
        return "MEDIUM"
    return "LOW"


def _normalise_records(source: Any) -> list[dict[str, Any]]:
    if isinstance(source, pd.DataFrame):
        return to_builtin(source.to_dict(orient="records"))
    if isinstance(source, dict):
        if isinstance(source.get("records"), list):
            return source["records"]
        if isinstance(source.get("tasks"), list):
            return source["tasks"]
        return [source]
    if isinstance(source, Iterable) and not isinstance(source, (str, bytes)):
        return [to_builtin(item) for item in source]
    return []


def generate_tasks_from_anomalies(
    source: Any,
    path: str | Path | None = None,
    *,
    threshold: float = 0.7,
) -> list[dict[str, Any]]:
    payload = ensure_tasks_file(path)
    tasks = payload.setdefault("tasks", [])
    existing_keys = {
        (
            str(task.get("meter_id", "")),
            str(task.get("detection_time", "")),
            str(task.get("status", "")).lower(),
        )
        for task in tasks
    }
    created: list[dict[str, Any]] = []
    for record in _normalise_records(source):
        anomaly_score = float(record.get("anomaly_score") or 0.0)
        status = str(record.get("status", "")).strip().lower()
        is_anomaly = int(record.get("is_anomaly") or 0) == 1
        is_suspicious = (
            status == "electricity theft"
            or status == "anomaly"
            or is_anomaly
        )
        if not is_suspicious:
            continue
        detection_time = str(record.get("timestamp") or record.get("detection_time") or "")
        meter_id = str(record.get("meter_id") or "").strip()
        if not meter_id:
            continue
        open_key = (meter_id, detection_time, "pending")
        assigned_key = (meter_id, detection_time, "assigned")
        completed_key = (meter_id, detection_time, "completed")
        if open_key in existing_keys or assigned_key in existing_keys or completed_key in existing_keys:
            continue
        task = {
            "task_id": f"task-{uuid4().hex[:12]}",
            "meter_id": meter_id,
            "customer_id": record.get("customer_id") or record.get("consumer_id"),
            "location": record.get("location") or record.get("area") or record.get("region") or "Unknown Area",
            "anomaly_score": round(anomaly_score, 4),
            "risk": risk_from_anomaly_score(anomaly_score),
            "assigned_to": "",
            "inspection_date": "",
            "inspection_time": "",
            "status": "Pending",
            "remarks": "",
            "detection_time": detection_time,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        tasks.append(task)
        existing_keys.add(open_key)
        created.append(task)
    save_json(payload, tasks_file_path(path))
    return created
