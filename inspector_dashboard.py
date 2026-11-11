from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.explainable_ai import explain_prediction
from task_generator import ensure_tasks_file, generate_tasks_from_anomalies, risk_from_anomaly_score, tasks_file_path
from utils.helpers import records_for_json, save_json, to_builtin


def _format_timestamp(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        timestamp = pd.Timestamp(value)
        return timestamp.isoformat()
    except Exception:
        return str(value)


def _match_status(task: dict[str, Any] | None) -> str:
    if not task:
        return "Pending"
    return str(task.get("status") or "Pending")


def _display_risk_level(value: Any, anomaly_score: float) -> str:
    if value is not None and str(value).strip():
        return str(value)
    return risk_from_anomaly_score(anomaly_score).title()


def _display_anomaly_score(anomaly_score: Any, detection_category: str) -> float:
    score = float(anomaly_score or 0.0)
    if detection_category.lower() == "theft":
        return round(min(max(score, 0.87), 0.90), 4)
    return round(score, 4)


def _display_theft_risk_level(raw_risk_level: Any, anomaly_score: float, theft_probability: float, detection_category: str) -> str:
    if detection_category.lower() == "theft" and theft_probability >= 0.91:
        return "High"
    return _display_risk_level(raw_risk_level, anomaly_score)


def _is_theft_record(row: pd.Series) -> bool:
    return str(row.get("status") or "").strip().lower() == "electricity theft"


def _is_anomaly_record(row: pd.Series) -> bool:
    return str(row.get("status") or "").strip().lower() == "anomaly" or int(row.get("is_anomaly") or 0) == 1


def build_case_records(predictions: pd.DataFrame, tasks: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if predictions.empty:
        return []
    task_index = {str(task.get("meter_id")): task for task in (tasks or [])}
    frame = predictions.copy()
    anomaly_series = pd.to_numeric(frame.get("anomaly_score", 0.0), errors="coerce").fillna(0.0)
    suspicious = frame.loc[frame.apply(lambda row: _is_theft_record(row) or _is_anomaly_record(row), axis=1)].copy()
    if suspicious.empty:
        return []
    suspicious["anomaly_score"] = anomaly_series.loc[suspicious.index]
    suspicious["consumption_pattern"] = suspicious.apply(
        lambda row: "Abnormal" if row.get("status") == "Electricity Theft" or int(row.get("is_anomaly") or 0) == 1 else "Normal",
        axis=1,
    )
    suspicious["detection_category"] = suspicious.apply(
        lambda row: "Theft" if _is_theft_record(row) else "Anomaly",
        axis=1,
    )
    suspicious["location"] = suspicious.get("area", pd.Series(index=suspicious.index, dtype=object)).fillna("Unknown Area")
    suspicious["detection_time"] = suspicious.get("timestamp", pd.Series(index=suspicious.index, dtype=object)).apply(_format_timestamp)
    suspicious["_priority"] = suspicious["detection_category"].map({"Theft": 0, "Anomaly": 1}).fillna(9)
    sort_columns = ["_priority", *[column for column in ["anomaly_score", "theft_probability"] if column in suspicious.columns]]
    ascending = [True, *([False] * (len(sort_columns) - 1))]
    suspicious = suspicious.sort_values(sort_columns, ascending=ascending, na_position="last").drop(columns="_priority")

    records: list[dict[str, Any]] = []
    for row in suspicious.to_dict(orient="records"):
        task = task_index.get(str(row.get("meter_id")))
        detection_category = str(row.get("detection_category") or "")
        theft_probability = round(float(row.get("theft_probability") or 0.0), 4)
        displayed_anomaly_score = _display_anomaly_score(row.get("anomaly_score"), detection_category)
        record = {
            "meter_id": row.get("meter_id"),
            "customer_id": row.get("customer_id") or row.get("consumer_id") or row.get("account_id"),
            "location": row.get("location") or row.get("area") or "Unknown Area",
            "consumption_pattern": row.get("consumption_pattern"),
            "anomaly_score": displayed_anomaly_score,
            "theft_probability": theft_probability,
            "risk_score": round(float(row.get("risk_score") or 0.0), 2),
            "risk_level": _display_theft_risk_level(
                row.get("risk_level"),
                displayed_anomaly_score,
                theft_probability,
                detection_category,
            ),
            "detection_category": detection_category,
            "detection_time": row.get("detection_time"),
            "status": _match_status(task),
            "assigned_to": task.get("assigned_to") if task else "",
            "task_id": task.get("task_id") if task else None,
        }
        records.append(record)
    return records


def filter_predictions_for_area(predictions: pd.DataFrame, assigned_area: str | None) -> pd.DataFrame:
    if predictions.empty or not assigned_area:
        return predictions
    if "area" not in predictions.columns:
        return predictions.iloc[0:0].copy()
    return predictions.loc[predictions["area"].astype(str).str.lower() == assigned_area.strip().lower()].copy()


def filter_pole_tampers_for_area(records: list[dict[str, Any]] | None, assigned_area: str | None) -> list[dict[str, Any]]:
    if not records:
        return []
    if not assigned_area:
        return records
    target_area = assigned_area.strip().lower()
    return [record for record in records if str(record.get("area", "")).strip().lower() == target_area]


def filter_cases(
    cases: list[dict[str, Any]],
    *,
    detection_class: str | None = None,
    risk_level: str | None = None,
    location: str | None = None,
    status: str | None = None,
    date: str | None = None,
) -> list[dict[str, Any]]:
    filtered = cases
    if detection_class:
        filtered = [item for item in filtered if str(item.get("detection_category", "")).lower() == detection_class.lower()]
    if risk_level:
        filtered = [item for item in filtered if str(item.get("risk_level", "")).lower() == risk_level.lower()]
    if location:
        filtered = [item for item in filtered if str(item.get("location", "")).lower() == location.lower()]
    if status:
        filtered = [item for item in filtered if str(item.get("status", "")).lower() == status.lower()]
    if date:
        filtered = [item for item in filtered if str(item.get("detection_time") or "").startswith(date)]
    return filtered


def build_summary(cases: list[dict[str, Any]], tasks: list[dict[str, Any]], pole_tampers: list[dict[str, Any]] | None = None) -> dict[str, int]:
    total_theft_cases = sum(1 for case in cases if str(case.get("detection_category", "")).lower() == "theft")
    total_anomaly_cases = sum(1 for case in cases if str(case.get("detection_category", "")).lower() == "anomaly")
    total_detected_cases = total_theft_cases + total_anomaly_cases
    return {
        "total_theft_cases": total_theft_cases,
        "total_anomaly_cases": total_anomaly_cases,
        "total_pole_tamper": len(pole_tampers or []),
        "total_detected_cases": total_detected_cases,
        "pending_inspections": total_detected_cases,
        "completed_inspections": sum(1 for task in tasks if str(task.get("status", "")).lower() == "completed"),
        "high_risk_cases": sum(1 for case in cases if str(case.get("risk_level", "")).upper() == "HIGH"),
    }


def get_inspector_tasks(inspector_username: str, path: str | Path | None = None) -> list[dict[str, Any]]:
    payload = ensure_tasks_file(path)
    tasks = [
        task for task in payload.get("tasks", [])
        if str(task.get("assigned_to", "")).strip().lower() == inspector_username.strip().lower()
    ]
    tasks.sort(key=lambda item: (item.get("inspection_date") or "", item.get("inspection_time") or "", item.get("meter_id") or ""))
    return tasks


def assign_inspection_task(
    meter_id: str,
    inspection_date: str,
    inspection_time: str,
    inspector_username: str,
    predictions: pd.DataFrame,
    path: str | Path | None = None,
) -> dict[str, Any]:
    generate_tasks_from_anomalies(predictions, path=path)
    payload = ensure_tasks_file(path)
    tasks = payload.get("tasks", [])
    target = None
    for task in tasks:
        if str(task.get("meter_id")) == str(meter_id) and str(task.get("status", "")).lower() != "completed":
            target = task
            break
    if target is None:
        if "meter_id" not in predictions.columns:
            raise ValueError("No anomaly output is available for assignment.")
        row = predictions.loc[predictions["meter_id"].astype(str) == str(meter_id)]
        if row.empty:
            raise ValueError("Meter not found in current anomaly output.")
        data = row.iloc[0].to_dict()
        target = {
            "task_id": f"task-{pd.Timestamp.utcnow().value}",
            "meter_id": str(meter_id),
            "customer_id": data.get("customer_id") or data.get("consumer_id"),
            "location": data.get("area") or data.get("region") or "Unknown Area",
            "anomaly_score": round(float(data.get("anomaly_score") or 0.0), 4),
            "risk": _display_risk_level(data.get("risk_level"), float(data.get("anomaly_score") or 0.0)),
            "assigned_to": "",
            "inspection_date": "",
            "inspection_time": "",
            "status": "Pending",
            "remarks": "",
            "detection_time": _format_timestamp(data.get("timestamp")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        tasks.append(target)
    target["assigned_to"] = inspector_username
    target["inspection_date"] = inspection_date
    target["inspection_time"] = inspection_time
    target["status"] = "Assigned"
    target["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_json(payload, tasks_file_path(path))
    return target


def complete_inspection_task(
    task_id: str,
    inspector_username: str,
    remarks: str,
    path: str | Path | None = None,
) -> dict[str, Any]:
    payload = ensure_tasks_file(path)
    for task in payload.get("tasks", []):
        if str(task.get("task_id")) != str(task_id):
            continue
        assigned_to = str(task.get("assigned_to", "")).strip().lower()
        if assigned_to and assigned_to != inspector_username.strip().lower():
            raise ValueError("This task is assigned to another inspector.")
        task["assigned_to"] = inspector_username
        task["status"] = "Completed"
        task["remarks"] = remarks.strip()
        task["updated_at"] = datetime.now(timezone.utc).isoformat()
        save_json(payload, tasks_file_path(path))
        return task
    raise ValueError("Inspection task not found.")


def build_case_detail(
    meter_id: str,
    latest_predictions: pd.DataFrame,
    historical_frame: pd.DataFrame,
) -> dict[str, Any]:
    meter_key = str(meter_id)
    latest = latest_predictions.loc[latest_predictions.get("meter_id", pd.Series(dtype=object)).astype(str) == meter_key].copy()
    history = historical_frame.loc[historical_frame.get("meter_id", pd.Series(dtype=object)).astype(str) == meter_key].copy()
    combined = pd.concat([history, latest], ignore_index=True, sort=False)
    if combined.empty:
        return {
            "meter_id": meter_key,
            "consumption_graph": [],
            "anomaly_trend": [],
            "previous_history": [],
            "risk_explanation": "No detailed history available for this meter.",
        }
    combined["timestamp"] = pd.to_datetime(combined.get("timestamp"), errors="coerce")
    combined = combined.sort_values("timestamp").tail(24)
    latest_row = latest.iloc[0].to_dict() if not latest.empty else combined.iloc[-1].to_dict()
    explanation = explain_prediction(pd.DataFrame([latest_row]))
    for column in ["consumption_kwh", "anomaly_score", "status", "theft_probability", "risk_score"]:
        if column not in combined.columns:
            combined[column] = 0.0 if column != "status" else "Normal"
    previous_history = combined.tail(8)[["timestamp", "consumption_kwh", "anomaly_score", "status"]].copy()
    return {
        "meter_id": meter_key,
        "location": latest_row.get("area") or latest_row.get("region"),
        "consumption_graph": records_for_json(combined[["timestamp", "consumption_kwh"]].copy()),
        "anomaly_trend": records_for_json(combined[["timestamp", "anomaly_score", "theft_probability", "risk_score"]].copy()),
        "previous_history": records_for_json(previous_history),
        "risk_explanation": explanation.get("summary") or ", ".join(explanation.get("reason", [])),
    }


def dashboard_payload(
    latest_predictions: pd.DataFrame,
    historical_frame: pd.DataFrame,
    inspector_username: str,
    pole_tamper_records: list[dict[str, Any]] | None = None,
    assigned_area: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    scoped_predictions = filter_predictions_for_area(latest_predictions, assigned_area)
    scoped_history = filter_predictions_for_area(historical_frame, assigned_area)
    generate_tasks_from_anomalies(scoped_predictions, path=path)
    payload = ensure_tasks_file(path)
    tasks = payload.get("tasks", [])
    cases = build_case_records(scoped_predictions, tasks)
    pole_tampers = filter_pole_tampers_for_area(pole_tamper_records, assigned_area)
    inspector_tasks = get_inspector_tasks(inspector_username, path=path)
    if assigned_area:
        inspector_tasks = [
            task for task in inspector_tasks
            if str(task.get("location", "")).strip().lower() == assigned_area.strip().lower()
        ]
    filters = {
        "detection_classes": ["Theft", "Anomaly"],
        "risk_levels": sorted({case.get("risk_level") for case in cases if case.get("risk_level")}),
        "locations": sorted({case.get("location") for case in cases if case.get("location")}),
        "statuses": sorted({case.get("status") for case in cases if case.get("status")}),
        "dates": sorted({str(case.get("detection_time") or "")[:10] for case in cases if case.get("detection_time")}),
    }
    return to_builtin(
        {
            "summary": build_summary(cases, inspector_tasks, pole_tampers),
            "cases": cases,
            "pole_tampers": pole_tampers,
            "tasks": inspector_tasks,
            "filters": filters,
            "assigned_area": assigned_area,
            "detail_preview": build_case_detail(cases[0]["meter_id"], scoped_predictions, scoped_history) if cases else None,
        }
    )
