from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.explainable_ai import explain_prediction
from src.preprocess import aggregate_region_consumption, build_overview_snapshot
from utils.helpers import ensure_project_dirs, records_for_json, save_json


def _predict_request_from_row(row: pd.Series) -> dict[str, Any]:
    return {
        "meter_id": row["meter_id"],
        "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], "isoformat") else str(row["timestamp"]),
        "region": row["region"],
        "area": row["area"],
        "latitude": float(row["latitude"]),
        "longitude": float(row["longitude"]),
        "voltage": float(row["voltage"]),
        "current": float(row["current"]),
        "power": float(row["power"]),
        "consumption_kwh": float(row["consumption_kwh"]),
        "power_factor": float(row["power_factor"]),
        "temperature": float(row["temperature"]),
        "humidity": float(row["humidity"]),
        "rainfall": float(row["rainfall"]),
        "wind_speed": float(row["wind_speed"]),
        "weather_condition": row["weather_condition"],
        # Keep the example request aligned with the public inference schema.
        # Ground-truth and generator-internal label fields must never be sent
        # to the prediction endpoint.
        "expected_consumption_kwh": float(row.get("expected_consumption_kwh", row["consumption_kwh"])),
        "wastage_score": float(row.get("wastage_score", 0.0)),
        "usage_profile": row.get("usage_profile", "residential"),
    }


def export_sample_outputs(
    predictions: pd.DataFrame,
    forecast: dict[str, Any] | None = None,
    output_dir: str | Path | None = None,
) -> Path:
    paths = ensure_project_dirs()
    output_dir = Path(output_dir) if output_dir else paths.root / "sample_outputs" / "generated"
    output_dir.mkdir(parents=True, exist_ok=True)

    if predictions.empty:
        save_json({"status": "empty", "message": "Run the project pipeline to generate sample outputs."}, output_dir / "manifest.json")
        return output_dir

    latest = predictions.copy()
    for column, default in [("theft_probability", 0.0), ("anomaly_score", 0.0), ("is_anomaly", 0), ("status", "Normal")]:
        if column not in latest.columns:
            latest[column] = default
    latest = latest.sort_values(["theft_probability", "anomaly_score"], ascending=False).reset_index(drop=True)
    request_row = latest.iloc[0]
    explanation = explain_prediction(pd.DataFrame([request_row]))

    predict_request = _predict_request_from_row(request_row)
    predict_response = [
        {
            "meter_id": request_row["meter_id"],
            "region": request_row["region"],
            "area": request_row["area"],
            "latitude": float(request_row["latitude"]),
            "longitude": float(request_row["longitude"]),
            "status": request_row["status"],
            "theft_probability": round(float(request_row["theft_probability"]), 4),
            "anomaly_score": round(float(request_row["anomaly_score"]), 4),
            "reason": explanation.get("reason", []),
        }
    ]

    theft_records = latest.loc[latest["status"] == "Electricity Theft"].head(5).copy()
    theft_records["reason"] = [
        explain_prediction(pd.DataFrame([row])).get("summary", "")
        for _, row in theft_records.iterrows()
    ]

    recent_consumption = (
        latest.groupby("timestamp", as_index=False)
        .agg(
            total_consumption=("consumption_kwh", "sum"),
            anomalies=("is_anomaly", "sum"),
            theft=("status", lambda values: int((values == "Electricity Theft").sum())),
        )
        .sort_values("timestamp")
    )

    overview = {
        "timestamp": request_row["timestamp"].isoformat() if hasattr(request_row["timestamp"], "isoformat") else str(request_row["timestamp"]),
        "summary": build_overview_snapshot(latest),
        "region_consumption": records_for_json(aggregate_region_consumption(latest)),
        "live_consumption": records_for_json(recent_consumption),
        "forecast": forecast or {"next_hour": 0.0, "next_day": 0.0, "next_week": 0.0, "series": []},
    }

    manifest = {
        "seed": 42,
        "description": "Reference outputs exported from the seeded smart-grid simulation.",
        "files": [
            "predict_request.json",
            "predict_response.json",
            "theft_response.json",
            "overview_response.json",
            "top_meter_snapshot.csv",
        ],
    }

    save_json(manifest, output_dir / "manifest.json")
    save_json(predict_request, output_dir / "predict_request.json")
    save_json(predict_response, output_dir / "predict_response.json")
    save_json({"records": records_for_json(theft_records), "count": int(len(theft_records))}, output_dir / "theft_response.json")
    save_json(overview, output_dir / "overview_response.json")
    latest.head(20).to_csv(output_dir / "top_meter_snapshot.csv", index=False)
    return output_dir
