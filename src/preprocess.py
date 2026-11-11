from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from utils.helpers import ensure_project_dirs


NUMERIC_COLUMNS = [
    "latitude",
    "longitude",
    "voltage",
    "current",
    "power",
    "consumption_kwh",
    "power_factor",
    "temperature",
    "humidity",
    "rainfall",
    "wind_speed",
    "is_theft",
    "expected_consumption_kwh",
    "wastage_score",
    "seeded_theft_probability",
]


def preprocess_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    if frame.empty:
        return frame

    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"]).sort_values(["meter_id", "timestamp"]).reset_index(drop=True)

    for column in NUMERIC_COLUMNS:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    existing_numeric = [column for column in NUMERIC_COLUMNS if column in frame.columns]
    frame[existing_numeric] = frame[existing_numeric].fillna(0.0)
    frame["power_factor"] = frame["power_factor"].clip(0.0, 1.0)
    frame["consumption_kwh"] = frame["consumption_kwh"].clip(lower=0.0)
    frame["wastage_score"] = frame["wastage_score"].clip(lower=0.0)
    frame["wastage_flag"] = ((frame["wastage_score"] >= 0.25) | (frame["power_factor"] < 0.8)).astype(int)
    frame["power_gap"] = (frame["power"] - frame["consumption_kwh"]).round(3)
    frame["temperature_band"] = pd.cut(
        frame["temperature"],
        bins=[-10, 20, 26, 32, 50],
        labels=["cool", "mild", "warm", "hot"],
    ).astype(str)
    return frame


def load_dataset(path: str | Path | None = None, nrows: int | None = None) -> pd.DataFrame:
    paths = ensure_project_dirs()
    target = Path(path) if path else paths.dataset
    if not target.exists():
        return pd.DataFrame()
    dataframe = pd.read_csv(target, nrows=nrows)
    return preprocess_frame(dataframe)


def load_training_dataset(max_rows: int = 50000) -> pd.DataFrame:
    paths = ensure_project_dirs()
    sample_path = paths.data_processed / "smart_meter_sample.csv"
    if sample_path.exists():
        frame = load_dataset(sample_path)
    else:
        frame = load_dataset(paths.dataset, nrows=max_rows)
    if frame.empty or len(frame) <= max_rows:
        return frame

    positives = frame[frame["is_theft"] == 1]
    negatives = frame[frame["is_theft"] == 0]
    positive_take = min(len(positives), max_rows // 3)
    negative_take = max_rows - positive_take
    sampled = pd.concat(
        [
            positives.sample(n=positive_take, random_state=42) if positive_take else positives.head(0),
            negatives.sample(n=min(len(negatives), negative_take), random_state=42),
        ],
        ignore_index=True,
    )
    return sampled.sample(frac=1.0, random_state=42).reset_index(drop=True)


def build_overview_snapshot(dataframe: pd.DataFrame) -> dict[str, float]:
    if dataframe.empty:
        return {"total_meters": 0, "active_meters": 0, "anomalies": 0, "theft": 0, "wastage": 0}
    latest = dataframe.sort_values("timestamp").groupby("meter_id", as_index=False).tail(1)
    return {
        "total_meters": int(dataframe["meter_id"].nunique()),
        "active_meters": int(latest["meter_id"].nunique()),
        "anomalies": int((latest.get("is_anomaly", pd.Series(dtype=int)) == 1).sum()),
        "theft": int((latest.get("status", pd.Series(dtype=object)) == "Electricity Theft").sum()),
        "wastage": int((latest.get("wastage_flag", pd.Series(dtype=int)) == 1).sum()),
    }


def limit_theft_alerts(dataframe: pd.DataFrame, max_alerts: int = 2, preferred_meter_id: str | None = None) -> pd.DataFrame:
    frame = dataframe.copy()
    if frame.empty or "status" not in frame.columns or max_alerts < 0:
        return frame

    theft_mask = frame["status"] == "Electricity Theft"
    theft_count = int(theft_mask.sum())
    if theft_count <= max_alerts:
        return frame

    sort_columns = [column for column in ["theft_probability", "risk_score", "anomaly_score"] if column in frame.columns]
    theft_frame = frame.loc[theft_mask].copy()
    if sort_columns:
        theft_frame = theft_frame.sort_values(sort_columns, ascending=False)
    keep_indexes = set(theft_frame.head(max_alerts).index.tolist())
    if preferred_meter_id and "meter_id" in theft_frame.columns:
        preferred_matches = theft_frame.loc[theft_frame["meter_id"].astype(str) == str(preferred_meter_id)]
        if not preferred_matches.empty:
            preferred_index = preferred_matches.index[0]
            keep_indexes.add(preferred_index)
            if len(keep_indexes) > max_alerts:
                fallback_indexes = [index for index in theft_frame.index.tolist() if index != preferred_index]
                keep_indexes = {preferred_index, *fallback_indexes[: max(0, max_alerts - 1)]}

    downgrade_mask = theft_mask & ~frame.index.isin(keep_indexes)
    if "theft_probability" in frame.columns:
        frame.loc[downgrade_mask, "theft_probability"] = pd.to_numeric(
            frame.loc[downgrade_mask, "theft_probability"],
            errors="coerce",
        ).fillna(0.0).clip(upper=0.89)

    anomaly_mask = pd.to_numeric(frame.get("is_anomaly", 0), errors="coerce").fillna(0).astype(int) == 1
    wastage_mask = pd.to_numeric(frame.get("wastage_score", 0.0), errors="coerce").fillna(0.0) >= 0.35

    frame.loc[downgrade_mask, "status"] = "Normal"
    frame.loc[downgrade_mask & wastage_mask, "status"] = "Power Wastage"
    frame.loc[downgrade_mask & anomaly_mask, "status"] = "Anomaly"
    return frame


def aggregate_weather_impact(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["temperature_band", "avg_consumption", "avg_wastage", "avg_humidity"])
    grouped = (
        dataframe.groupby("temperature_band", dropna=False)
        .agg(
            avg_consumption=("consumption_kwh", "mean"),
            avg_wastage=("wastage_score", "mean"),
            avg_humidity=("humidity", "mean"),
        )
        .reset_index()
    )
    return grouped.sort_values("temperature_band").reset_index(drop=True)


def aggregate_region_consumption(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["area", "consumption_kwh"])
    frame = dataframe.copy()
    if "area" not in frame.columns:
        frame["area"] = "Unknown"
    if "consumption_kwh" not in frame.columns:
        frame["consumption_kwh"] = 0.0
    return (
        frame.groupby("area", as_index=False)
        .agg(consumption_kwh=("consumption_kwh", "sum"))
        .sort_values("consumption_kwh", ascending=False)
        .reset_index(drop=True)
    )
