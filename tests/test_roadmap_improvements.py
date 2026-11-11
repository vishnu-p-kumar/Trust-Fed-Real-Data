from __future__ import annotations
import numpy as np
import pandas as pd
import pytest
from src.security.privacy import clip_update, gaussian_dp_aggregate, simulated_secure_sum
from src.jobs.sqlite_queue import SQLiteJobQueue
from scripts.evaluate_theft_models import evaluate
from scripts.evaluate_forecasting import evaluate as evaluate_forecast
from scripts.validate_theft_dataset import validate


def test_clip_update_respects_norm():
    clipped = clip_update(np.array([3.0, 4.0]), 1.0)
    assert np.linalg.norm(clipped) == pytest.approx(1.0)


def test_gaussian_aggregate_is_reproducible_and_reports_limitations():
    updates = [np.array([1.0, 2.0]), np.array([2.0, 3.0])]
    left = gaussian_dp_aggregate(updates, max_norm=1, noise_multiplier=2, seed=7)
    right = gaussian_dp_aggregate(updates, max_norm=1, noise_multiplier=2, seed=7)
    np.testing.assert_allclose(left["aggregate"], right["aggregate"])
    assert left["privacy"]["composed_rounds_accounted"] is False


def test_simulated_secure_sum_masks_cancel():
    updates = {"a": np.array([1.0, 2.0]), "b": np.array([3.0, 4.0]), "c": np.array([5.0, 6.0])}
    secrets = {("a", "b"): b"a"*32, ("a", "c"): b"b"*32, ("b", "c"): b"c"*32}
    np.testing.assert_allclose(simulated_secure_sum(updates, secrets), np.array([9.0, 12.0]), atol=1e-8)


def test_sqlite_queue_lifecycle(tmp_path):
    queue = SQLiteJobQueue(tmp_path / "jobs.db")
    created = queue.enqueue("report", {"meter": "M1"})
    assert created["status"] == "queued"
    claimed = queue.claim()
    assert claimed["id"] == created["id"] and claimed["status"] == "running"
    finished = queue.finish(created["id"], {"ok": True})
    assert finished["status"] == "completed" and finished["result"]["ok"] is True


def test_group_holdout_evaluation_has_no_customer_overlap():
    rng = np.random.default_rng(1)
    n = 120
    y = np.array([0, 1] * (n // 2))
    frame = pd.DataFrame({"customer_id": [f"C{i}" for i in range(n)], "is_theft": y,
                          "d001": y + rng.normal(0, .1, n), "d002": rng.normal(0, 1, n)})
    result = evaluate(frame, seed=4)
    assert result["customer_overlap"] == 0
    assert set(result["metrics"]) == {"logistic_regression", "random_forest", "hist_gradient_boosting"}


def test_forecast_benchmarks_are_chronological():
    frame = pd.DataFrame({"timestamp": pd.date_range("2025-01-01", periods=100, freq="h"),
                          "consumption_kwh": np.arange(100, dtype=float)})
    result = evaluate_forecast(frame, seasonal_period=24)
    assert result["train_observations"] + result["test_observations"] == 100
    assert "persistence" in result["metrics"]


def test_dataset_validator_requires_provenance(tmp_path):
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"customer_id": ["a", "b", "c", "d"], "is_theft": [0, 1, 0, 1]}).to_csv(csv_path, index=False)
    with pytest.raises(ValueError, match="Provenance manifest"):
        validate(csv_path, tmp_path / "manifest.json")


def test_api_rejects_untrusted_cross_origin_and_sets_security_headers(monkeypatch):
    import asyncio
    from fastapi.testclient import TestClient
    from api import main as api_main

    async def idle_loop():
        while True:
            await asyncio.sleep(60)

    monkeypatch.setattr(api_main.runtime, "bootstrap", lambda: None)
    monkeypatch.setattr(api_main.runtime, "send_telegram_status", lambda *args, **kwargs: {"status": "skipped"})
    monkeypatch.setattr(api_main.runtime, "simulation_loop", idle_loop)
    with TestClient(api_main.app) as client:
        rejected = client.post("/auth/logout", headers={"Origin": "https://attacker.invalid"})
        health = client.get("/health")
    assert rejected.status_code == 403
    assert health.headers.get("x-content-type-options") == "nosniff"
    assert health.headers.get("x-frame-options") == "SAMEORIGIN"


def test_dataset_validator_returns_checksum_and_declared_provenance(tmp_path):
    csv_path = tmp_path / "data.csv"
    pd.DataFrame({"CONS_NO": ["a", "b", "c", "d"], "FLAG": [0, 1, 0, 1]}).to_csv(csv_path, index=False)
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"source_name":"test","source_url":"https://example.org/data","license":"test-only","label_provenance":"inspection labels","label_verification":"provider documentation"}')
    report = validate(csv_path, manifest)
    assert report["rows"] == 4
    assert report["unique_meters"] == 4
    assert len(report["sha256"]) == 64


def test_federated_experiment_supports_partial_client_participation_and_hatta_weight():
    from src.federated.experiment import run_experiment
    result = run_experiment({"seed": 19, "clients": 6, "rounds": 2, "local_epochs": 1,
        "samples": 240, "features": 8, "partition": "severe", "attack": "none",
        "client_participation": 0.5, "hatta_trust_weight": 0.75})
    assert result["efficiency"]["mean_participants_per_round"] == 3
    assert result["efficiency"]["client_participation"] == 0.5
    assert "hatta" in result["metrics"]
    assert all(0 <= result["metrics"]["hatta"][key] <= 1 for key in
               ("accuracy", "precision", "recall", "f1", "pr_auc", "roc_auc", "false_positive_rate"))


def test_federated_experiment_rejects_invalid_participation_and_hatta_weight():
    from src.federated.experiment import run_experiment
    with pytest.raises(ValueError, match="client_participation"):
        run_experiment({"clients": 4, "rounds": 1, "samples": 120, "client_participation": 0})
    with pytest.raises(ValueError, match="hatta_trust_weight"):
        run_experiment({"clients": 4, "rounds": 1, "samples": 120, "hatta_trust_weight": 1.5})


def test_generalization_evaluator_reports_location_season_and_temporal_splits():
    from scripts.evaluate_generalization import evaluate_generalization
    rng=np.random.default_rng(9); rows=[]
    for city in ("North", "South", "East"):
        for meter in range(12):
            label=meter%2
            for day in range(120):
                date=pd.Timestamp("2025-01-01")+pd.Timedelta(days=day)
                rows.append({"meter_id":f"{city}-{meter}","city":city,"timestamp":date,
                    "is_theft":label,"voltage":230+rng.normal(0,2)+label*4,
                    "current":5+rng.normal(0,1)+label*2})
    result=evaluate_generalization(pd.DataFrame(rows),seeds=(11,23))
    assert set(result["cross_location"])=={"East","North","South"}
    assert result["temporal_drift"] is not None
    assert all(item["customer_overlap"]==0 for item in result["cross_location"].values())
    assert all(0<=run["f1"]<=1 for item in result["cross_location"].values() for run in item["runs"])
