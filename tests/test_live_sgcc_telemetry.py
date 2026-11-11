from __future__ import annotations

import numpy as np
import pandas as pd

from src.sgcc_live_model import FEATURE_COLUMNS, SGCCLiveTheftDetector, extract_window_features
from api import main as api_main


def test_sgcc_live_feature_extractor_has_stable_26_feature_schema():
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    values = np.linspace(1.0, 2.0, 30)
    frame = extract_window_features(values, dates)
    assert frame.shape == (1, 26)
    assert frame.columns.tolist() == FEATURE_COLUMNS
    assert np.isfinite(frame.select_dtypes(include=["number"]).to_numpy()).all()


def test_sgcc_detector_requires_full_history_then_scores_bundled_model():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    detector = SGCCLiveTheftDetector(
        root / "models/sgcc_live_theft_model.pkl",
        root / "models/sgcc_live_theft_metadata.json",
    )
    dates = pd.date_range("2026-01-01", periods=29, freq="D")
    history = pd.Series(np.full(29, 1.5), index=dates)
    pending = detector.score_daily_history(history)
    assert pending["ready"] is False
    assert pending["status"] == "Insufficient History"
    assert pending["required_history_days"] == 30

    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    history = pd.Series(np.full(30, 1.5), index=dates)
    scored = detector.score_daily_history(history)
    assert scored["ready"] is True
    assert 0.0 <= scored["theft_probability"] <= 1.0
    assert scored["model_source"] == "SGCC labelled benchmark"


def test_ceew_forecaster_scores_live_daily_history():
    from pathlib import Path
    from src.ceew_forecaster import CEEWConsumptionForecaster
    root = Path(__file__).resolve().parents[1]
    forecaster = CEEWConsumptionForecaster(
        root / "models/ceew_consumption_forecaster.pkl",
        root / "models/ceew_consumption_forecaster_metadata.json",
    )
    dates = pd.date_range("2026-01-01", periods=10, freq="D")
    history = pd.Series(np.linspace(1.0, 2.0, 10), index=dates)
    result = forecaster.forecast_next_day(history)
    assert result["ready"] is True
    assert result["forecast_date"].startswith("2026-01-11")
    assert result["predicted_consumption_kwh"] >= 0
    assert result["training_dataset"].startswith("CEEW")


def test_runtime_ingests_meter_history_and_updates_prediction_state(monkeypatch):
    class FakeDetector:
        def score_daily_history(self, daily):
            if len(daily) < 30:
                return {"ready": False, "status": "Insufficient History", "history_days": len(daily), "valid_days": len(daily)}
            return {"ready": True, "status": "Electricity Theft", "history_days": 30,
                    "valid_days": 30, "theft_probability": 0.82, "model_source": "SGCC labelled benchmark"}

    class FakeForecaster:
        selected_forecaster = "test_ceew_model"
        def forecast_next_day(self, daily):
            return {"ready": True, "forecast_date": "2026-02-01T00:00:00", "predicted_consumption_kwh": 1.7,
                    "training_dataset": "CEEW Mathura and Bareilly daily aggregates"}

    monkeypatch.setattr(api_main, "dataframe_to_sqlite", lambda *args, **kwargs: None)
    runtime = api_main.SmartGridRuntime()
    runtime.live_mode = True
    runtime.demo_mode = False
    runtime.live_detector = FakeDetector()
    runtime.ceew_forecaster = FakeForecaster()
    runtime.latest_predictions = pd.DataFrame()
    runtime.prediction_buffer.clear()
    records = [
        {"meter_id": "LIVE-TEST-1", "timestamp": date.isoformat(), "consumption_kwh": 1.5,
         "voltage": 230.0, "power_factor": 0.92, "area": "Test Area", "region": "Test Region"}
        for date in pd.date_range("2026-01-01", periods=30, freq="D")
    ]
    result = runtime.ingest_telemetry_records(records)
    assert result["accepted_readings"] == 30
    assert result["meters_scored"] == 1
    prediction = result["results"][0]
    assert prediction["status"] == "Electricity Theft"
    assert prediction["theft_probability"] == 0.82
    assert prediction["next_day_forecast_kwh"] == 1.7
    assert runtime.latest_predictions.iloc[0]["meter_id"] == "LIVE-TEST-1"


def test_live_runtime_health_reports_sgcc_as_default_model_source():
    runtime = api_main.SmartGridRuntime()
    runtime.live_mode = True
    runtime.demo_mode = False
    health = runtime.health_payload()
    assert health["runtime_mode"] == "live_telemetry"
    assert health["model_source"] == "SGCC labelled benchmark"
    assert health["minimum_history_days"] == 30
    assert health["data_provenance"]["ceew_theft_labels_verified"] is False


def test_sgcc_detector_rejects_only_19_valid_days_even_when_window_is_30_days():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    detector = SGCCLiveTheftDetector(
        root / "models/sgcc_live_theft_model.pkl",
        root / "models/sgcc_live_theft_metadata.json",
    )
    dates = pd.date_range("2026-01-01", periods=30, freq="D")
    values = np.full(30, 1.5)
    values[:11] = np.nan
    result = detector.score_daily_history(pd.Series(values, index=dates))
    assert result["ready"] is False
    assert result["status"] == "Insufficient History"
    assert result["history_days"] == 30
    assert result["valid_days"] == 19


def test_electrical_anomaly_can_be_flagged_before_theft_model_warmup(monkeypatch):
    class FakeDetector:
        def score_daily_history(self, daily):
            return {"ready": False, "status": "Insufficient History", "history_days": 1,
                    "valid_days": 1, "required_history_days": 30}

    class FakeForecaster:
        selected_forecaster = "test_ceew_model"
        def forecast_next_day(self, daily):
            return {"ready": False, "reason": "Need seven daily readings"}

    monkeypatch.setattr(api_main, "dataframe_to_sqlite", lambda *args, **kwargs: None)
    runtime = api_main.SmartGridRuntime()
    runtime.live_mode = True
    runtime.demo_mode = False
    runtime.live_detector = FakeDetector()
    runtime.ceew_forecaster = FakeForecaster()
    runtime.latest_predictions = pd.DataFrame()
    record = {"meter_id": "EARLY-ANOMALY-1", "timestamp": "2026-01-01T12:00:00Z",
              "consumption_kwh": 0.2, "voltage": 275.0, "power_factor": 0.95}
    result = runtime.ingest_telemetry_records([record])["results"][0]
    assert result["status"] == "Anomaly"
    assert result["electrical_anomaly"] is True
    assert result["theft_probability"] is None

