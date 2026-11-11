from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


RISK_LEVELS = [
    (35.0, "Low"),
    (60.0, "Medium"),
    (80.0, "High"),
    (101.0, "Critical"),
]


def _series_or_default(dataframe: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column in dataframe.columns:
        return pd.to_numeric(dataframe[column], errors="coerce").fillna(default)
    return pd.Series(default, index=dataframe.index, dtype=float)


def _normalise_series(series: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(series, errors="coerce").fillna(0.0).clip(lower=0.0)
    maximum = float(numeric.max()) if not numeric.empty else 0.0
    minimum = float(numeric.min()) if not numeric.empty else 0.0
    if maximum <= 1.0 and minimum >= 0.0:
        return numeric.clip(0.0, 1.0)
    if np.isclose(maximum, minimum):
        return pd.Series(0.0, index=numeric.index, dtype=float)
    return ((numeric - minimum) / (maximum - minimum)).clip(0.0, 1.0)


def _risk_level(score: float) -> str:
    for threshold, label in RISK_LEVELS:
        if score < threshold:
            return label
    return "Critical"


def score_meter_risk(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    if frame.empty:
        frame["risk_score"] = pd.Series(dtype=float)
        frame["risk_level"] = pd.Series(dtype=object)
        frame["risk_summary"] = pd.Series(dtype=object)
        return frame

    anomaly_component = _normalise_series(_series_or_default(frame, "anomaly_score"))
    rf_component = _normalise_series(_series_or_default(frame, "random_forest_probability"))
    boost_component = _normalise_series(_series_or_default(frame, "xgboost_probability"))
    theft_component = _normalise_series(
        0.45 * rf_component
        + 0.55 * boost_component
        + 0.20 * _normalise_series(_series_or_default(frame, "theft_probability"))
    )
    voltage_component = _normalise_series(_series_or_default(frame, "voltage_irregularity"))
    night_component = _normalise_series(_series_or_default(frame, "night_usage_ratio"))

    weighted_risk = (
        0.35 * anomaly_component
        + 0.35 * theft_component
        + 0.15 * voltage_component
        + 0.15 * night_component
    )

    dominant_factor = pd.DataFrame(
        {
            "anomaly": anomaly_component,
            "theft_probability": theft_component,
            "voltage_irregularity": voltage_component,
            "night_usage_ratio": night_component,
        }
    ).idxmax(axis=1)

    frame["risk_score"] = (weighted_risk * 100.0).round(2)
    frame["risk_level"] = frame["risk_score"].apply(_risk_level)
    frame["risk_summary"] = dominant_factor.map(
        {
            "anomaly": "Anomaly-driven risk",
            "theft_probability": "Theft probability dominated",
            "voltage_irregularity": "Voltage irregularity dominated",
            "night_usage_ratio": "High night usage dominated",
        }
    )
    return frame


def risk_distribution_by_area(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["area", "avg_risk_score", "critical_count", "high_count", "meter_count"])
    frame = dataframe if "risk_score" in dataframe.columns else score_meter_risk(dataframe)
    frame = frame.copy()
    if "area" not in frame.columns:
        frame["area"] = "Unknown"
    if "risk_level" not in frame.columns:
        frame["risk_level"] = frame.get("risk_score", pd.Series(0.0, index=frame.index)).apply(_risk_level)
    if "meter_id" not in frame.columns:
        frame["meter_id"] = frame.index.astype(str)
    return (
        frame.groupby("area", as_index=False)
        .agg(
            avg_risk_score=("risk_score", "mean"),
            critical_count=("risk_level", lambda values: int((values == "Critical").sum())),
            high_count=("risk_level", lambda values: int((values == "High").sum())),
            meter_count=("meter_id", "nunique"),
        )
        .sort_values(["avg_risk_score", "critical_count"], ascending=False)
        .reset_index(drop=True)
    )


def risk_payload(dataframe: pd.DataFrame, limit: int = 25) -> dict[str, Any]:
    frame = dataframe if "risk_score" in dataframe.columns else score_meter_risk(dataframe)
    sort_columns = [column for column in ["risk_score", "theft_probability"] if column in frame.columns]
    ranked = frame.sort_values(sort_columns, ascending=False).head(limit) if sort_columns else frame.head(limit)
    summary = {
        "critical": int((frame.get("risk_level", pd.Series(dtype=object)) == "Critical").sum()),
        "high": int((frame.get("risk_level", pd.Series(dtype=object)) == "High").sum()),
        "medium": int((frame.get("risk_level", pd.Series(dtype=object)) == "Medium").sum()),
        "low": int((frame.get("risk_level", pd.Series(dtype=object)) == "Low").sum()),
    }
    return {
        "summary": summary,
        "distribution": risk_distribution_by_area(frame).replace({np.nan: None}).to_dict(orient="records"),
        "records": ranked.replace({np.nan: None}).to_dict(orient="records"),
    }
