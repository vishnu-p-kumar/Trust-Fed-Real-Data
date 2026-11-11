from __future__ import annotations

import pandas as pd

import inspector_dashboard as inspector_ui
from inspector_dashboard import assign_inspection_task, complete_inspection_task, dashboard_payload, get_inspector_tasks
from inspector_manager import create_inspector, get_all_inspectors
from login import authenticate_user
from task_generator import ensure_tasks_file, generate_tasks_from_anomalies


def test_authenticate_user_requires_configured_admin_and_supports_inspector(tmp_path, monkeypatch) -> None:
    users_path = tmp_path / "users.json"
    monkeypatch.setenv("SMARTGRID_ADMIN_PASSWORD", "unit-test-admin-password")

    inspector = create_inspector("Field One", "inspector1", "secret123", "Area A", "1242950500", path=users_path)
    admin = authenticate_user("admin@gmail.com", "unit-test-admin-password", path=users_path)
    field_user = authenticate_user("inspector1", "secret123", path=users_path)

    assert inspector["username"] == "inspector1"
    assert inspector["assigned_area"] == "Area A"
    assert inspector["chat_id"] == "1242950500"
    assert admin is not None
    assert admin["role"] == "admin"
    assert field_user is not None
    assert field_user["role"] == "inspector"
    assert field_user["assigned_area"] == "Area A"
    assert field_user["chat_id"] == "1242950500"
    assert len(get_all_inspectors(path=users_path)) == 1


def test_task_generation_assignment_and_completion_flow(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR001",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.95,
                "theft_probability": 0.91,
            },
            {
                "meter_id": "MTR002",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area B",
                "status": "Normal",
                "is_anomaly": 0,
                "anomaly_score": 0.12,
                "theft_probability": 0.08,
            },
        ]
    )

    created = generate_tasks_from_anomalies(predictions, path=tasks_path)
    duplicate_run = generate_tasks_from_anomalies(predictions, path=tasks_path)
    assigned = assign_inspection_task("MTR001", "2026-05-10", "10:00 AM", "inspector1", predictions, path=tasks_path)
    my_tasks = get_inspector_tasks("inspector1", path=tasks_path)
    completed = complete_inspection_task(assigned["task_id"], "inspector1", "Meter seal tampered.", path=tasks_path)

    assert len(created) == 1
    assert duplicate_run == []
    assert assigned["status"] == "Assigned"
    assert len(my_tasks) == 1
    assert completed["status"] == "Completed"
    assert completed["remarks"] == "Meter seal tampered."
    assert ensure_tasks_file(tasks_path)["tasks"][0]["meter_id"] == "MTR001"


def test_dashboard_payload_surfaces_summary_filters_and_detail(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(inspector_ui, "explain_prediction", lambda *_args, **_kwargs: {"summary": "High anomaly concentration"})
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR001",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.95,
                "theft_probability": 0.91,
                "risk_score": 91.0,
                "consumption_kwh": 0.64,
            }
        ]
    )
    history = pd.DataFrame(
        [
            {
                "meter_id": "MTR001",
                "timestamp": "2026-05-10T08:00:00",
                "area": "Area A",
                "status": "Normal",
                "anomaly_score": 0.15,
                "theft_probability": 0.2,
                "risk_score": 42.0,
                "consumption_kwh": 1.24,
            }
        ]
    )

    payload = dashboard_payload(latest_predictions, history, "inspector1", path=tasks_path)

    assert payload["summary"]["total_theft_cases"] == 1
    assert payload["summary"]["high_risk_cases"] == 1
    assert payload["filters"]["locations"] == ["Area A"]
    assert payload["detail_preview"]["meter_id"] == "MTR001"
    assert payload["detail_preview"]["risk_explanation"] == "High anomaly concentration"


def test_inspector_dashboard_ignores_high_score_meter_without_detection(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR001",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.95,
                "theft_probability": 0.91,
                "risk_score": 91.0,
                "consumption_kwh": 0.64,
            },
            {
                "meter_id": "MTR002",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area B",
                "status": "Normal",
                "is_anomaly": 0,
                "anomaly_score": 0.98,
                "theft_probability": 0.12,
                "risk_score": 44.0,
                "consumption_kwh": 1.24,
            },
        ]
    )

    payload = dashboard_payload(latest_predictions, pd.DataFrame(), "inspector1", path=tasks_path)

    assert [case["meter_id"] for case in payload["cases"]] == ["MTR001"]
    assert payload["summary"]["total_theft_cases"] == 1
    assert payload["summary"]["total_anomaly_cases"] == 0
    assert payload["summary"]["total_detected_cases"] == 1


def test_filter_cases_supports_detection_class_and_priority(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR100",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Anomaly",
                "is_anomaly": 1,
                "anomaly_score": 0.82,
                "theft_probability": 0.31,
                "risk_score": 70.0,
                "consumption_kwh": 0.91,
            },
            {
                "meter_id": "MTR001",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.95,
                "theft_probability": 0.91,
                "risk_score": 91.0,
                "consumption_kwh": 0.64,
            },
        ]
    )

    payload = dashboard_payload(latest_predictions, pd.DataFrame(), "inspector1", path=tasks_path)
    theft_only = inspector_ui.filter_cases(payload["cases"], detection_class="Theft")
    anomaly_only = inspector_ui.filter_cases(payload["cases"], detection_class="Anomaly")

    assert [case["meter_id"] for case in payload["cases"]] == ["MTR001", "MTR100"]
    assert payload["summary"]["total_theft_cases"] == 1
    assert payload["summary"]["total_anomaly_cases"] == 1
    assert payload["summary"]["pending_inspections"] == 2
    assert [case["meter_id"] for case in theft_only] == ["MTR001"]
    assert [case["meter_id"] for case in anomaly_only] == ["MTR100"]


def test_inspector_dashboard_preserves_runtime_risk_level_from_admin_data(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR009",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area C",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.96,
                "theft_probability": 0.91,
                "risk_score": 22.0,
                "risk_level": "Low",
                "consumption_kwh": 0.64,
            }
        ]
    )

    payload = dashboard_payload(latest_predictions, pd.DataFrame(), "inspector1", path=tasks_path)

    assert payload["cases"][0]["meter_id"] == "MTR009"
    assert payload["cases"][0]["anomaly_score"] == 0.9
    assert payload["cases"][0]["theft_probability"] == 0.91
    assert payload["cases"][0]["risk_level"] == "High"


def test_inspector_dashboard_clamps_theft_anomaly_score_to_requested_band(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTR777",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area X",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.52,
                "theft_probability": 0.95,
                "risk_score": 80.0,
                "risk_level": "Medium",
                "consumption_kwh": 0.64,
            }
        ]
    )

    payload = dashboard_payload(latest_predictions, pd.DataFrame(), "inspector1", path=tasks_path)

    assert payload["cases"][0]["anomaly_score"] == 0.87
    assert payload["cases"][0]["risk_level"] == "High"


def test_inspector_dashboard_scopes_cases_to_assigned_area(tmp_path) -> None:
    tasks_path = tmp_path / "inspection_tasks.json"
    latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "MTRA1",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.92,
                "theft_probability": 0.93,
                "risk_score": 85.0,
                "risk_level": "High",
                "consumption_kwh": 0.64,
            },
            {
                "meter_id": "MTRB1",
                "timestamp": "2026-05-10T09:00:00",
                "area": "Area B",
                "status": "Anomaly",
                "is_anomaly": 1,
                "anomaly_score": 0.78,
                "theft_probability": 0.21,
                "risk_score": 60.0,
                "risk_level": "Medium",
                "consumption_kwh": 0.82,
            },
        ]
    )

    payload = dashboard_payload(latest_predictions, pd.DataFrame(), "inspector1", assigned_area="Area A", path=tasks_path)

    assert payload["assigned_area"] == "Area A"
    assert [case["meter_id"] for case in payload["cases"]] == ["MTRA1"]
    assert payload["filters"]["locations"] == ["Area A"]
