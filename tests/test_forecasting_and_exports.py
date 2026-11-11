from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.demand_forecasting import forecast_horizons, train_lstm_forecaster
from src.sample_outputs import export_sample_outputs
from api.main import MeterReading
import json


def test_forecast_falls_back_without_tensorflow(sample_meter_frame: pd.DataFrame, tmp_path: Path) -> None:
    metadata_path = tmp_path / "demand_metadata.json"
    model_path = tmp_path / "lstm_model.h5"
    metadata = train_lstm_forecaster(
        sample_meter_frame,
        lookback=3,
        epochs=1,
        model_path=model_path,
        metadata_path=metadata_path,
    )
    forecast = forecast_horizons(metadata_path=metadata_path, model_path=model_path, horizon=12)
    assert metadata["model_type"] in {"baseline", "lstm"}
    assert set(["next_hour", "next_day", "next_week", "series"]).issubset(forecast.keys())


def test_export_sample_outputs_writes_files(monkeypatch, sample_meter_frame: pd.DataFrame, tmp_path: Path) -> None:
    predictions = sample_meter_frame.copy()
    predictions["anomaly_score"] = 0.42
    predictions["theft_probability"] = 0.88
    predictions["status"] = "Electricity Theft"

    monkeypatch.setattr(
        "src.sample_outputs.explain_prediction",
        lambda frame: {
            "meter_id": frame.iloc[0]["meter_id"],
            "area": frame.iloc[0]["area"],
            "reason": ["Sudden consumption shift", "Voltage irregularity"],
            "summary": "Sudden consumption shift, Voltage irregularity",
        },
    )

    output_dir = export_sample_outputs(predictions, forecast={"next_hour": 10.0, "next_day": 240.0, "next_week": 1680.0, "series": []}, output_dir=tmp_path)
    assert (output_dir / "manifest.json").exists()
    assert (output_dir / "predict_request.json").exists()
    assert (output_dir / "predict_response.json").exists()
    assert (output_dir / "theft_response.json").exists()
    assert (output_dir / "overview_response.json").exists()

    # The exported example request must be accepted by the live inference schema.
    request = json.loads((output_dir / "predict_request.json").read_text(encoding="utf-8"))
    validated = MeterReading.model_validate(request)
    assert validated.meter_id == request["meter_id"]
    assert "is_theft" not in request
    assert "theft_type" not in request
    assert "seeded_theft_probability" not in request

