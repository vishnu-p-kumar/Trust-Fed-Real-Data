from __future__ import annotations

import asyncio

import pandas as pd
import pytest
from fastapi.testclient import TestClient
from fastapi import WebSocketDisconnect
from pydantic import ValidationError

from api import main as api_main
from src.preprocess import build_overview_snapshot


def test_prediction_schema_rejects_synthetic_label_and_bounds_inputs() -> None:
    base = {"meter_id":"M1","area":"Whitefield","latitude":12.9,"longitude":77.6,"voltage":230,"current":4,
            "power":1,"consumption_kwh":1,"power_factor":.9,"temperature":25,"humidity":50,"rainfall":0,"wind_speed":1,
            "weather_condition":"Clear"}
    api_main.MeterReading.model_validate(base)
    with pytest.raises(ValidationError):
        api_main.MeterReading.model_validate({**base,"seeded_theft_probability":.99})
    with pytest.raises(ValidationError):
        api_main.MeterReading.model_validate({**base,"voltage":900})


async def _idle_loop() -> None:
    while True:
        await asyncio.sleep(60)


def test_health_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(api_main.runtime, "bootstrap", lambda: None)
    monkeypatch.setattr(api_main.runtime, "send_telegram_status", lambda *args, **kwargs: {"provider": "telegram", "status": "skipped"})
    monkeypatch.setattr(api_main.runtime, "simulation_loop", _idle_loop)
    monkeypatch.setattr(
        api_main.runtime,
        "health_payload",
        lambda: {
            "status": "ok",
            "timestamp": "2026-03-12T18:00:00",
            "current_tick": None,
            "websocket_clients": 0,
            "artifacts": {"dataset": False},
        },
    )

    with TestClient(api_main.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_research_routes_require_admin_and_return_run_result(monkeypatch) -> None:
    monkeypatch.setattr(api_main.runtime, "bootstrap", lambda: None)
    monkeypatch.setattr(api_main.runtime, "send_telegram_status", lambda *args, **kwargs: {"status": "skipped"})
    monkeypatch.setattr(api_main.runtime, "simulation_loop", _idle_loop)
    request_data = {"clients":3,"rounds":1,"local_epochs":1,"partition":"iid","attack":"none"}
    with TestClient(api_main.app) as client:
        denied = client.post("/api/research/experiments", json=request_data)
    assert denied.status_code == 401

    monkeypatch.setattr(api_main, "_require_role", lambda _request, role: {"role": role})
    captured = {}
    def fake_run_experiment(config, output_dir, dataframe=None):
        captured["dataframe"] = dataframe
        return {"config": config, "metrics": {"fedavg": {"f1": .5}}, "privacy": {"enabled": False}}
    monkeypatch.setattr(api_main, "run_experiment", fake_run_experiment)
    with TestClient(api_main.app) as client:
        response = client.post("/api/research/experiments", json=request_data)
        assert response.status_code == 200
        run_id = response.json()["run_id"]
        detail = client.get(f"/api/research/experiments/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["metrics"]["fedavg"]["f1"] == .5
    assert captured["dataframe"] is not None
    assert {"meter_id", "is_theft"}.issubset(captured["dataframe"].columns)
    provenance = response.json()["dataset_provenance"]
    assert provenance["dataset"] == "SGCC labelled historical benchmark"
    assert provenance["synthetic_training"] is False


def test_pole_endpoints(monkeypatch) -> None:
    monkeypatch.setattr(api_main.runtime, "bootstrap", lambda: None)
    monkeypatch.setattr(api_main.runtime, "send_telegram_status", lambda *args, **kwargs: {"provider": "telegram", "status": "skipped"})
    monkeypatch.setattr(api_main.runtime, "simulation_loop", _idle_loop)
    monkeypatch.setattr(api_main, "_require_user", lambda _request: {"role": "admin"})
    monkeypatch.setattr(
        api_main.runtime,
        "pole_status_payload",
        lambda limit=20: {"summary": {"pole_count": 2, "suspicious_poles": 1}, "records": [{"pole_id": "P0001"}][:limit], "timeline": []},
    )
    monkeypatch.setattr(
        api_main.runtime,
        "pole_tamper_alerts_payload",
        lambda limit=20: {"count": 1, "records": [{"pole_id": "P0001", "message": "Pole P0001 energy mismatch detected."}][:limit]},
    )
    monkeypatch.setattr(
        api_main.runtime,
        "pole_energy_balance_payload",
        lambda limit=120: {"records": [{"pole_id": "P0001", "energy_gap": 1.2}][:limit], "heatmap": [{"pole_id": "P0001"}]},
    )

    with TestClient(api_main.app) as client:
        status_response = client.get("/api/pole-status")
        alerts_response = client.get("/api/pole-tamper-alerts")
        balance_response = client.get("/api/pole-energy-balance")

    assert status_response.status_code == 200
    assert status_response.json()["summary"]["suspicious_poles"] == 1
    assert alerts_response.status_code == 200
    assert alerts_response.json()["count"] == 1
    assert balance_response.status_code == 200
    assert balance_response.json()["heatmap"][0]["pole_id"] == "P0001"


def test_advance_tick_dispatches_all_detected_theft_and_pole_tamper_alerts(monkeypatch) -> None:
    runtime = api_main.SmartGridRuntime()
    runtime.demo_mode = False
    runtime.timeline = [pd.Timestamp("2026-04-13T08:00:00")]
    runtime.cursor = 0
    runtime.simulation_source = pd.DataFrame([{"timestamp": pd.Timestamp("2026-04-13T08:00:00"), "meter_id": "seed"}])
    runtime.historical_frame = pd.DataFrame([{"timestamp": pd.Timestamp("2026-04-13T07:00:00"), "meter_id": "hist", "area": "Area A"}])
    runtime.historical_pole_frame = pd.DataFrame([{"timestamp": pd.Timestamp("2026-04-13T07:00:00"), "pole_id": "P0", "area": "Area A"}])
    runtime.pole_catalog = pd.DataFrame()

    predictions = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "timestamp": "2026-04-13T08:00:00",
                "area": "Area A",
                "status": "Electricity Theft",
                "risk_level": "Medium",
                "risk_score": 52.0,
                "theft_probability": 0.91,
                "anomaly_score": 0.4,
            },
            {
                "meter_id": "M2",
                "timestamp": "2026-04-13T08:00:00",
                "area": "Area B",
                "status": "Electricity Theft",
                "risk_level": "Low",
                "risk_score": 48.0,
                "theft_probability": 0.89,
                "anomaly_score": 0.2,
            },
        ]
    )
    pole_status = pd.DataFrame(
        [
            {
                "timestamp": "2026-04-13T08:00:00",
                "pole_id": "P1",
                "area": "Area C",
                "tamper_probability": 0.97,
                "tamper_flag": 1,
            }
        ]
    )
    captured: dict[str, object] = {}

    monkeypatch.setenv("SMARTGRID_ENABLE_ALERTS", "1")
    def fail_if_demo_override_runs(_frame):
        raise AssertionError("research mode must not inject a theft candidate")

    monkeypatch.setattr(api_main, "_ensure_visible_theft_candidate", fail_if_demo_override_runs)
    monkeypatch.setattr(api_main, "classify_meter_events", lambda _frame: predictions.copy())
    monkeypatch.setattr(api_main, "limit_theft_alerts", lambda frame, max_alerts=2, preferred_meter_id=None: frame)
    monkeypatch.setattr(api_main, "_prioritize_sticky_meter", lambda frame, meter_id, sort_columns, ascending=None: frame)
    monkeypatch.setattr(api_main, "score_meter_risk", lambda frame: frame)
    monkeypatch.setattr(api_main, "calculate_efficiency_metrics", lambda frame: frame)
    monkeypatch.setattr(api_main, "simulate_pole_energy", lambda frame, pole_catalog=None: frame)
    monkeypatch.setattr(api_main, "detect_pole_tampering", lambda current_frame, historical_frame: pole_status.copy())
    monkeypatch.setattr(api_main, "generate_drift_report", lambda reference_frame, current_frame: {"drift_detected": False})
    monkeypatch.setattr(runtime, "_build_forecast_payload", lambda: {"next_hour": 0.0})

    def fake_dispatch(frame: pd.DataFrame, limit=None):
        captured["frame"] = frame.copy()
        captured["limit"] = limit
        return [{"provider": "telegram", "status": "sent", "count": len(frame), "recipients": 3}]

    monkeypatch.setattr(api_main, "dispatch_alerts", fake_dispatch)

    runtime.advance_tick()

    sent_frame = captured["frame"]
    assert captured["limit"] is None
    assert list(sent_frame["area"]) == ["Area A", "Area B", "Area C"]
    assert list(sent_frame.get("status", pd.Series(dtype=object)).fillna(""))[:2] == ["Electricity Theft", "Electricity Theft"]
    assert runtime.cached_alert_results == [{"provider": "telegram", "status": "sent", "count": 3, "recipients": 3}]


def test_add_inspector_sends_telegram_welcome_message(monkeypatch) -> None:
    monkeypatch.setattr(api_main.runtime, "bootstrap", lambda: None)
    monkeypatch.setattr(api_main.runtime, "send_telegram_status", lambda *args, **kwargs: {"provider": "telegram", "status": "skipped"})
    monkeypatch.setattr(api_main.runtime, "simulation_loop", _idle_loop)
    monkeypatch.setattr(api_main, "_require_role", lambda _request, role: {"role": role, "username": "admin"})
    monkeypatch.setattr(
        api_main,
        "create_inspector",
        lambda name, username, password, assigned_area, chat_id: {
            "id": "ins-123",
            "name": name,
            "username": username,
            "assigned_area": assigned_area,
            "chat_id": chat_id,
            "role": "inspector",
            "created_at": "2026-04-23T03:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        api_main,
        "send_inspector_welcome_message",
        lambda inspector: {"provider": "telegram", "status": "sent", "recipients": 1, "count": 1},
    )

    with TestClient(api_main.app) as client:
        response = client.post(
            "/api/inspectors",
            json={
                "name": "Field One",
                "username": "inspector1",
                "password": "secret123",
                "assigned_area": "Area A",
                "chat_id": "1242950500",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["inspector"]["username"] == "inspector1"
    assert payload["notification"] == {"provider": "telegram", "status": "sent", "recipients": 1, "count": 1}


def test_overview_snapshot_uses_wastage_flag() -> None:
    frame = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "timestamp": "2026-03-12T01:00:00",
                "is_anomaly": 0,
                "status": "Normal",
                "wastage_flag": 1,
            },
            {
                "meter_id": "M2",
                "timestamp": "2026-03-12T01:00:00",
                "is_anomaly": 1,
                "status": "Electricity Theft",
                "wastage_flag": 0,
            },
        ]
    )

    summary = build_overview_snapshot(frame)

    assert summary["wastage"] == 1
    assert summary["anomalies"] == 1
    assert summary["theft"] == 1


def test_current_tick_payloads_ignore_recent_history(monkeypatch) -> None:
    latest = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Whitefield",
                "region": "Bengaluru",
                "status": "Electricity Theft",
                "is_anomaly": 0,
                "anomaly_score": 0.12,
                "theft_probability": 0.91,
                "risk_score": 88.5,
                "latitude": 12.97,
                "longitude": 77.75,
                "wastage_flag": 1,
                "efficiency_score": 60.0,
                "estimated_losses_kwh": 2.5,
            },
            {
                "meter_id": "M2",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Koramangala",
                "region": "Bengaluru",
                "status": "Anomaly",
                "is_anomaly": 1,
                "anomaly_score": 0.66,
                "theft_probability": 0.33,
                "risk_score": 58.0,
                "latitude": 12.93,
                "longitude": 77.62,
                "wastage_flag": 0,
                "efficiency_score": 92.0,
                "estimated_losses_kwh": 0.4,
            },
        ]
    )
    historical = pd.DataFrame(
        [
            {
                "meter_id": "OLD1",
                "timestamp": "2026-03-12T01:00:00",
                "area": "Indiranagar",
                "region": "Bengaluru",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.72,
                "theft_probability": 0.96,
                "risk_score": 91.0,
                "latitude": 12.97,
                "longitude": 77.64,
                "wastage_flag": 1,
                "efficiency_score": 55.0,
                "estimated_losses_kwh": 3.2,
            }
        ]
    )

    monkeypatch.setattr(api_main, "explain_prediction", lambda *_args, **_kwargs: {"summary": "test"})

    runtime = api_main.SmartGridRuntime()
    runtime.latest_predictions = latest
    runtime.prediction_buffer.clear()
    runtime.prediction_buffer.append(historical)

    theft = runtime.theft_payload(limit=10)
    anomalies = runtime.anomaly_payload(limit=10)
    efficiency = runtime.efficiency_payload(limit=10)
    overview = runtime.overview_payload()

    assert theft["count"] == 1
    assert theft["records"][0]["meter_id"] == "M1"
    assert anomalies["count"] == 1
    assert anomalies["records"][0]["meter_id"] == "M2"
    assert efficiency["summary"]["low_efficiency"] == 1
    assert overview["summary"]["theft"] == 1
    assert overview["summary"]["anomalies"] == 1
    assert overview["summary"]["wastage"] == 1


def test_meter_payload_includes_coordinates_for_dashboard_heatmap() -> None:
    runtime = api_main.SmartGridRuntime()
    runtime.latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Whitefield",
                "status": "Normal",
                "latitude": 12.97,
                "longitude": 77.75,
                "consumption_kwh": 1.4,
                "power": 1.2,
                "voltage": 230.0,
                "power_factor": 0.96,
                "anomaly_score": 0.05,
                "theft_probability": 0.08,
                "risk_score": 12.0,
                "risk_level": "Low",
                "efficiency_score": 94.0,
            }
        ]
    )

    meters = runtime.meter_payload(limit=10)

    assert meters[0]["latitude"] == 12.97
    assert meters[0]["longitude"] == 77.75


def test_theft_and_anomaly_payload_counts_are_not_limited(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "explain_prediction", lambda *_args, **_kwargs: {"summary": "test"})

    runtime = api_main.SmartGridRuntime()
    runtime.latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": f"M{i}",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Whitefield" if i < 3 else "Koramangala",
                "region": "Bengaluru",
                "status": "Electricity Theft" if i < 4 else "Anomaly",
                "is_anomaly": 1 if i >= 2 else 0,
                "anomaly_score": 0.2 + i * 0.1,
                "theft_probability": 0.85 if i < 4 else 0.2,
                "risk_score": 82.0 if i < 3 else 65.0,
                "latitude": 12.9,
                "longitude": 77.6,
                "wastage_flag": 0,
                "efficiency_score": 90.0,
                "estimated_losses_kwh": 0.5,
                "consumption_kwh": 1.0,
            }
            for i in range(5)
        ]
    )

    theft = runtime.theft_payload(limit=2)
    anomalies = runtime.anomaly_payload(limit=1)

    assert len(theft["records"]) == 2
    assert theft["count"] == 4
    assert theft["summary"]["count"] == 4
    assert theft["summary"]["critical_areas"] == 1
    assert len(anomalies["records"]) == 1
    assert anomalies["count"] == 3
    assert anomalies["summary"]["count"] == 3


def test_visible_theft_candidate_is_injected_only_when_needed() -> None:
    frame = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "status": "Normal",
                "theft_probability": 0.12,
                "random_forest_probability": 0.08,
                "xgboost_probability": 0.16,
                "anomaly_score": 0.25,
                "wastage_score": 0.05,
                "seeded_theft_probability": 0.0,
            },
            {
                "meter_id": "M2",
                "status": "Anomaly",
                "theft_probability": 0.28,
                "random_forest_probability": 0.21,
                "xgboost_probability": 0.33,
                "anomaly_score": 0.52,
                "wastage_score": 0.12,
                "seeded_theft_probability": 0.0,
            },
        ]
    )

    promoted = api_main._ensure_visible_theft_candidate(frame)

    assert int((promoted["status"] == "Electricity Theft").sum()) == 1
    assert float(promoted.loc[promoted["status"] == "Electricity Theft", "theft_probability"].iloc[0]) >= 0.91

    existing = frame.copy()
    existing.loc[0, "status"] = "Electricity Theft"
    untouched = api_main._ensure_visible_theft_candidate(existing)

    assert int((untouched["status"] == "Electricity Theft").sum()) == 1


def test_runtime_keeps_first_detected_theft_meter_sticky() -> None:
    runtime = api_main.SmartGridRuntime()

    first_tick = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "status": "Electricity Theft",
                "theft_probability": 0.93,
                "random_forest_probability": 0.9,
                "xgboost_probability": 0.95,
                "anomaly_score": 0.4,
            },
            {
                "meter_id": "M2",
                "status": "Normal",
                "theft_probability": 0.2,
                "random_forest_probability": 0.18,
                "xgboost_probability": 0.22,
                "anomaly_score": 0.3,
            },
        ]
    )
    runtime._capture_sticky_theft_meter(first_tick)

    second_tick = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "status": "Normal",
                "theft_probability": 0.12,
                "random_forest_probability": 0.11,
                "xgboost_probability": 0.14,
                "anomaly_score": 0.18,
            },
            {
                "meter_id": "M2",
                "status": "Electricity Theft",
                "theft_probability": 0.88,
                "random_forest_probability": 0.82,
                "xgboost_probability": 0.91,
                "anomaly_score": 0.52,
            },
        ]
    )

    sticky = runtime._apply_sticky_theft_meter(second_tick)

    sticky_row = sticky.loc[sticky["meter_id"] == "M1"].iloc[0]
    assert runtime.sticky_theft_meter_id == "M1"
    assert sticky_row["status"] == "Electricity Theft"
    assert float(sticky_row["theft_probability"]) >= 0.91


def test_sticky_theft_sort_key_prioritises_locked_meter() -> None:
    frame = pd.DataFrame(
        [
            {"meter_id": "M1", "theft_probability": 0.81, "anomaly_score": 0.2},
            {"meter_id": "M2", "theft_probability": 0.95, "anomaly_score": 0.7},
        ]
    )

    sticky_key = api_main._sticky_theft_sort_key(frame, "M1")
    ordered = (
        frame.assign(_sticky_theft_priority=sticky_key)
        .sort_values(by=["_sticky_theft_priority", "theft_probability", "anomaly_score"], ascending=[False, False, False])
        .drop(columns="_sticky_theft_priority")
    )

    assert ordered.iloc[0]["meter_id"] == "M1"


def test_limit_theft_alerts_preserves_preferred_meter() -> None:
    frame = pd.DataFrame(
        [
            {"meter_id": "M1", "status": "Electricity Theft", "theft_probability": 0.91, "anomaly_score": 0.2, "is_anomaly": 0, "wastage_score": 0.1},
            {"meter_id": "M2", "status": "Electricity Theft", "theft_probability": 0.97, "anomaly_score": 0.7, "is_anomaly": 1, "wastage_score": 0.4},
            {"meter_id": "M3", "status": "Electricity Theft", "theft_probability": 0.95, "anomaly_score": 0.5, "is_anomaly": 1, "wastage_score": 0.2},
        ]
    )

    limited = api_main.limit_theft_alerts(frame, max_alerts=2, preferred_meter_id="M1")
    kept_meters = set(limited.loc[limited["status"] == "Electricity Theft", "meter_id"].tolist())

    assert kept_meters == {"M1", "M2"}


def test_theft_payload_prioritises_sticky_meter(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "explain_prediction", lambda *_args, **_kwargs: {"summary": "test"})

    runtime = api_main.SmartGridRuntime()
    runtime.sticky_theft_meter_id = "M1"
    runtime.latest_predictions = pd.DataFrame(
        [
            {
                "meter_id": "M1",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Whitefield",
                "region": "Bengaluru",
                "status": "Electricity Theft",
                "is_anomaly": 0,
                "anomaly_score": 0.31,
                "theft_probability": 0.91,
                "risk_score": 70.0,
                "latitude": 12.97,
                "longitude": 77.75,
            },
            {
                "meter_id": "M2",
                "timestamp": "2026-03-12T02:00:00",
                "area": "Koramangala",
                "region": "Bengaluru",
                "status": "Electricity Theft",
                "is_anomaly": 1,
                "anomaly_score": 0.66,
                "theft_probability": 0.96,
                "risk_score": 92.0,
                "latitude": 12.93,
                "longitude": 77.62,
            },
        ]
    )

    theft = runtime.theft_payload(limit=10)

    assert theft["records"][0]["meter_id"] == "M1"


def test_register_client_unregisters_when_initial_snapshot_send_fails(monkeypatch) -> None:
    class DummySocket:
        async def accept(self) -> None:
            return None

        async def send_json(self, _payload) -> None:
            raise WebSocketDisconnect(code=1006)

    runtime = api_main.SmartGridRuntime()
    monkeypatch.setattr(runtime, "snapshot_message", lambda: {"type": "live_tick"})
    socket = DummySocket()

    try:
        asyncio.run(runtime.register_client(socket))  # type: ignore[arg-type]
    except WebSocketDisconnect:
        pass

    assert socket not in runtime.ws_clients


def test_pole_payload_helpers_surface_latest_runtime_state() -> None:
    runtime = api_main.SmartGridRuntime()
    runtime.latest_pole_status = pd.DataFrame(
        [
            {
                "timestamp": "2026-03-12T02:00:00",
                "pole_id": "P0001",
                "transformer_id": "T001",
                "area": "Whitefield",
                "supplied_energy": 14.2,
                "meter_energy_sum": 10.3,
                "loss_estimate": 0.4,
                "energy_gap": 3.5,
                "tamper_probability": 0.91,
                "tamper_flag": 1,
                "pole_event_type": "illegal_connection",
            },
            {
                "timestamp": "2026-03-12T02:00:00",
                "pole_id": "P0002",
                "transformer_id": "T001",
                "area": "Koramangala",
                "supplied_energy": 9.4,
                "meter_energy_sum": 8.8,
                "loss_estimate": 0.3,
                "energy_gap": 0.3,
                "tamper_probability": 0.22,
                "tamper_flag": 0,
                "pole_event_type": "normal",
            },
        ]
    )
    runtime.recent_pole_status = runtime.latest_pole_status.copy()

    status = runtime.pole_status_payload(limit=10)
    alerts = runtime.pole_tamper_alerts_payload(limit=10)
    balance = runtime.pole_energy_balance_payload(limit=10)

    assert status["summary"]["pole_count"] == 2
    assert status["summary"]["suspicious_poles"] == 1
    assert alerts["count"] == 1
    assert alerts["records"][0]["pole_id"] == "P0001"
    assert balance["heatmap"][0]["pole_id"] in {"P0001", "P0002"}
