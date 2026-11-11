from __future__ import annotations

import numpy as np
import pandas as pd

from utils.helpers import BASE_FEATURE_COLUMNS, CATEGORICAL_COLUMNS


DEFAULT_FEATURE_VALUES = {
    "voltage": 230.0,
    "current": 0.0,
    "power": 0.0,
    "consumption_kwh": 0.0,
    "power_factor": 1.0,
    "temperature": 25.0,
    "humidity": 50.0,
    "rainfall": 0.0,
    "wind_speed": 0.0,
    "expected_consumption_kwh": 0.0,
    "wastage_score": 0.0,
    "region": "Bengaluru",
    "area": "Unknown Area",
    "weather_condition": "Clear",
    "usage_profile": "residential",
}


def add_engineered_features(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    if frame.empty:
        return frame

    for column, default in DEFAULT_FEATURE_VALUES.items():
        if column not in frame.columns:
            frame[column] = default

    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    else:
        frame["timestamp"] = pd.NaT

    frame = frame.sort_values(["meter_id", "timestamp"]).reset_index(drop=True)
    frame["hour_of_day"] = frame["timestamp"].dt.hour
    frame["day_of_week"] = frame["timestamp"].dt.dayofweek

    grouped = frame.groupby("meter_id", group_keys=False)
    frame["rolling_average_consumption"] = grouped["consumption_kwh"].transform(lambda series: series.rolling(24, min_periods=1).mean())
    frame["consumption_variance"] = grouped["consumption_kwh"].transform(lambda series: series.rolling(24, min_periods=2).var().fillna(0.0))
    # Past-only reference: a full-series maximum leaks future readings into earlier predictions.
    past_peak = grouped["consumption_kwh"].transform(lambda series: series.cummax().shift(1))
    frame["peak_usage_ratio"] = frame["consumption_kwh"] / past_peak.replace(0.0, np.nan)

    night_mask = ((frame["hour_of_day"] >= 22) | (frame["hour_of_day"] <= 5)).astype(float)
    frame["_night_consumption"] = frame["consumption_kwh"] * night_mask
    rolling_night = grouped["_night_consumption"].transform(lambda series: series.rolling(24, min_periods=1).sum())
    rolling_total = grouped["consumption_kwh"].transform(lambda series: series.rolling(24, min_periods=1).sum()).replace(0.0, np.nan)
    frame["night_usage_ratio"] = rolling_night / rolling_total

    weather_load = frame["temperature"].abs() + frame["humidity"] / 100.0 + frame["rainfall"] * 0.8 + frame["wind_speed"] * 0.6 + 1.0
    frame["weather_consumption_ratio"] = frame["consumption_kwh"] / weather_load
    frame["power_factor_loss"] = 1.0 - frame["power_factor"].clip(0.0, 1.0)
    frame["voltage_irregularity"] = (frame["voltage"] - 230.0).abs() / 230.0
    frame["current_power_gap"] = (frame["power"] - frame["consumption_kwh"]).abs()

    numeric_cols = [
        "rolling_average_consumption",
        "consumption_variance",
        "peak_usage_ratio",
        "night_usage_ratio",
        "weather_consumption_ratio",
        "power_factor_loss",
        "voltage_irregularity",
        "current_power_gap",
    ]
    frame[numeric_cols] = frame[numeric_cols].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame = frame.drop(columns=["_night_consumption"])
    return frame


def build_feature_matrix(
    dataframe: pd.DataFrame,
    model_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    enriched = add_engineered_features(dataframe)
    if enriched.empty:
        return enriched, pd.DataFrame(columns=model_columns or [])

    feature_frame = enriched[BASE_FEATURE_COLUMNS + CATEGORICAL_COLUMNS].copy()
    encoded = pd.get_dummies(feature_frame, columns=CATEGORICAL_COLUMNS, dtype=float)
    encoded = encoded.replace([np.inf, -np.inf], np.nan).fillna(0.0)

    if model_columns is not None:
        encoded = encoded.reindex(columns=model_columns, fill_value=0.0)
    return enriched, encoded
