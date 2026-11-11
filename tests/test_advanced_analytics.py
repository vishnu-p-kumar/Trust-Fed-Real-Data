from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.energy_efficiency import calculate_efficiency_metrics
from src.feature_engineering import build_feature_matrix
from src.risk_scoring import score_meter_risk
from src.transformer_forecasting import forecast_transformer_horizons, train_transformer_forecaster


def _expanded_meter_frame(sample_meter_frame: pd.DataFrame) -> pd.DataFrame:
    template = sample_meter_frame.loc[sample_meter_frame["meter_id"] == "M0001"].copy()
    variations = [
        ("M0101", "Whitefield", "residential", 0.9, 0.15, 0.05),
        ("M0102", "Electronic City", "commercial", 1.7, 0.45, 0.12),
        ("M0103", "Peenya Industrial Area", "industrial", 2.8, 0.78, 0.24),
        ("M0104", "Koramangala", "night_usage", 1.4, 0.88, 0.18),
    ]
    frames = []
    for meter_id, area, profile, scale, theft_probability, anomaly_score in variations:
        frame = template.copy()
        frame["meter_id"] = meter_id
        frame["area"] = area
        frame["usage_profile"] = profile
        frame["consumption_kwh"] = frame["consumption_kwh"] * scale
        frame["power"] = frame["power"] * scale
        frame["expected_consumption_kwh"] = frame["expected_consumption_kwh"] * max(scale - 0.08, 0.4)
        frame["wastage_score"] = 0.32 if profile == "night_usage" else 0.08
        frame["seeded_theft_probability"] = theft_probability
        frame["temperature"] = frame["temperature"] + scale
        frame["humidity"] = frame["humidity"] + scale * 2
        frame["voltage"] = frame["voltage"] - scale
        frame["power_factor"] = 0.82 if profile == "industrial" else 0.92
        frames.append(frame)
    expanded = pd.concat(frames, ignore_index=True)
    enriched, _ = build_feature_matrix(expanded)
    enriched["anomaly_score"] = (
        enriched["meter_id"].map({"M0101": 0.05, "M0102": 0.18, "M0103": 0.32, "M0104": 0.41}).fillna(0.0)
    )
    enriched["random_forest_probability"] = (
        enriched["meter_id"].map({"M0101": 0.11, "M0102": 0.49, "M0103": 0.67, "M0104": 0.85}).fillna(0.0)
    )
    enriched["xgboost_probability"] = (
        enriched["meter_id"].map({"M0101": 0.16, "M0102": 0.53, "M0103": 0.74, "M0104": 0.91}).fillna(0.0)
    )
    enriched["theft_probability"] = (0.45 * enriched["random_forest_probability"] + 0.55 * enriched["xgboost_probability"]).round(4)
    enriched["status"] = enriched["meter_id"].map(
        {
            "M0104": "Electricity Theft",
            "M0103": "Anomaly",
        }
    ).fillna("Normal")
    return enriched


def test_risk_scoring_generates_score_and_level(sample_meter_frame: pd.DataFrame) -> None:
    enriched = _expanded_meter_frame(sample_meter_frame)
    scored = score_meter_risk(enriched)
    assert scored["risk_score"].between(0, 100).all()
    assert set(scored["risk_level"].unique()).issubset({"Low", "Medium", "High", "Critical"})
    assert scored.loc[scored["meter_id"] == "M0104", "risk_score"].mean() > scored.loc[scored["meter_id"] == "M0101", "risk_score"].mean()


def test_efficiency_metrics_flag_low_efficiency(sample_meter_frame: pd.DataFrame) -> None:
    enriched = _expanded_meter_frame(sample_meter_frame)
    scored = calculate_efficiency_metrics(score_meter_risk(enriched))
    assert "efficiency_score" in scored.columns
    assert scored["efficiency_score"].between(0, 100).all()
    assert int(scored["wastage_flag"].sum()) >= 1


def test_transformer_forecast_pipeline_returns_expected_shape(sample_meter_frame: pd.DataFrame, tmp_path: Path) -> None:
    metadata_path = tmp_path / "transformer_metadata.json"
    model_path = tmp_path / "transformer_forecaster.pt"
    enriched = _expanded_meter_frame(sample_meter_frame)
    metadata = train_transformer_forecaster(
        enriched,
        lookback=3,
        epochs=1,
        model_path=model_path,
        metadata_path=metadata_path,
    )
    forecast = forecast_transformer_horizons(metadata_path=metadata_path, model_path=model_path, horizon=12)
    assert metadata["model_type"] in {"baseline", "transformer"}
    assert set(["next_hour", "next_day", "next_week", "series"]).issubset(forecast.keys())
    assert len(forecast["series"]) <= 12
