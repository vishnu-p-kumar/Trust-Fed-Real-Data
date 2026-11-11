from __future__ import annotations

from hashlib import sha256
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_TECHNICAL_LOSS_RATE = 0.035
DEFAULT_MISMATCH_THRESHOLD = 0.12


def build_pole_catalog_from_meters(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["transformer_id", "pole_id", "area", "meter_count", "connected_meters"])

    frame = dataframe.copy()
    if "transformer_id" not in frame.columns:
        frame["transformer_id"] = "T000"
    if "pole_id" not in frame.columns:
        frame["pole_id"] = frame["meter_id"].astype(str)

    return (
        frame.groupby(["transformer_id", "pole_id", "area"], as_index=False)
        .agg(
            meter_count=("meter_id", "nunique"),
            connected_meters=("meter_id", lambda values: "|".join(sorted(pd.Series(values).astype(str).unique().tolist()))),
        )
        .sort_values(["transformer_id", "pole_id"])
        .reset_index(drop=True)
    )


def _stable_rng(*parts: Any) -> np.random.Generator:
    seed_input = "|".join(str(part) for part in parts)
    digest = sha256(seed_input.encode("utf-8")).hexdigest()
    return np.random.default_rng(int(digest[:16], 16))


def simulate_pole_energy(
    meter_frame: pd.DataFrame,
    pole_catalog: pd.DataFrame | None = None,
    technical_loss_rate: float = DEFAULT_TECHNICAL_LOSS_RATE,
    mismatch_threshold: float = DEFAULT_MISMATCH_THRESHOLD,
) -> pd.DataFrame:
    if meter_frame.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "transformer_id",
                "pole_id",
                "area",
                "meter_count",
                "meter_energy_sum",
                "technical_losses",
                "energy_supplied",
                "energy_gap",
                "energy_gap_ratio",
                "illegal_load_kwh",
                "load_spike_kwh",
                "pole_event_type",
                "possible_pole_tamper",
            ]
        )

    frame = meter_frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    if "transformer_id" not in frame.columns:
        frame["transformer_id"] = "T000"
    if "pole_id" not in frame.columns:
        frame["pole_id"] = frame["meter_id"].astype(str)
    if "area" not in frame.columns:
        frame["area"] = "Unknown"
    # Prediction frames intentionally exclude the synthetic/ground-truth `is_theft`
    # label. Treat it as absent rather than crashing or inferring truth from a score.
    # The label is only used when explicitly supplied by a dataset-generation/test path.
    if "is_theft" not in frame.columns:
        frame["is_theft"] = 0

    catalog = pole_catalog.copy() if pole_catalog is not None and not pole_catalog.empty else build_pole_catalog_from_meters(frame)
    catalog = catalog[["transformer_id", "pole_id", "area", "meter_count", "connected_meters"]].drop_duplicates()

    grouped = (
        frame.groupby(["timestamp", "transformer_id", "pole_id", "area"], as_index=False)
        .agg(
            meter_energy_sum=("consumption_kwh", "sum"),
            meter_power_sum=("power", "sum"),
            theft_count=("is_theft", "sum"),
            meter_count_seen=("meter_id", "nunique"),
        )
        .sort_values(["timestamp", "transformer_id", "pole_id"])
        .reset_index(drop=True)
    )
    grouped = grouped.merge(catalog, on=["transformer_id", "pole_id", "area"], how="left")
    grouped["meter_count"] = pd.to_numeric(grouped["meter_count"], errors="coerce").fillna(grouped["meter_count_seen"]).clip(lower=1)

    illegal_loads: list[float] = []
    spike_loads: list[float] = []
    event_types: list[str] = []
    for _, row in grouped.iterrows():
        timestamp = pd.Timestamp(row["timestamp"]).strftime("%Y-%m-%d %H:%M:%S")
        rng = _stable_rng(row["pole_id"], timestamp, int(row["meter_count"]), round(float(row["meter_energy_sum"]), 3))
        theft_present = int(row.get("theft_count", 0)) > 0
        illegal_event = theft_present or rng.random() < 0.07
        spike_event = rng.random() < 0.1
        illegal_load = float(rng.uniform(0.4, 2.8) * max(float(row["meter_count"]), 1.0) * 0.35) if illegal_event else 0.0
        spike_load = float(rng.uniform(0.3, 1.6) * max(float(row["meter_energy_sum"]), 0.8) * 0.18) if spike_event else 0.0
        event_type = "illegal_connection" if illegal_load > 0 and illegal_load >= spike_load else "abnormal_load_increase" if spike_load > 0 else "normal"
        illegal_loads.append(round(illegal_load, 3))
        spike_loads.append(round(spike_load, 3))
        event_types.append(event_type)

    grouped["illegal_load_kwh"] = illegal_loads
    grouped["load_spike_kwh"] = spike_loads
    grouped["pole_event_type"] = event_types
    grouped["technical_losses"] = (
        grouped["meter_energy_sum"].astype(float) * float(technical_loss_rate)
        + grouped["meter_power_sum"].astype(float).clip(lower=0.0) * 0.01
    ).round(3)
    grouped["energy_supplied"] = (
        grouped["meter_energy_sum"].astype(float)
        + grouped["technical_losses"].astype(float)
        + grouped["illegal_load_kwh"].astype(float)
        + grouped["load_spike_kwh"].astype(float)
    ).round(3)
    grouped["energy_gap"] = (
        grouped["energy_supplied"].astype(float)
        - (grouped["meter_energy_sum"].astype(float) + grouped["technical_losses"].astype(float))
    ).round(3)
    grouped["energy_gap_ratio"] = (
        grouped["energy_gap"].astype(float) / grouped["energy_supplied"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0).round(4)
    grouped["possible_pole_tamper"] = (grouped["energy_gap_ratio"] >= float(mismatch_threshold)).astype(int)

    preferred_columns = [
        "timestamp",
        "transformer_id",
        "pole_id",
        "area",
        "meter_count",
        "connected_meters",
        "meter_energy_sum",
        "meter_power_sum",
        "technical_losses",
        "energy_supplied",
        "energy_gap",
        "energy_gap_ratio",
        "illegal_load_kwh",
        "load_spike_kwh",
        "pole_event_type",
        "possible_pole_tamper",
    ]
    return grouped[preferred_columns].reset_index(drop=True)
