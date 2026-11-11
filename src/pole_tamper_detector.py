from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from src.pole_monitoring import DEFAULT_MISMATCH_THRESHOLD, simulate_pole_energy


def _ensure_pole_energy_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe.copy()
    if {"energy_supplied", "meter_energy_sum", "energy_gap"}.issubset(dataframe.columns):
        frame = dataframe.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        return frame.dropna(subset=["timestamp"]).reset_index(drop=True)
    return simulate_pole_energy(dataframe)


def _predict_ml_anomaly_score(history: pd.DataFrame, current: pd.DataFrame) -> np.ndarray:
    feature_columns = [
        "energy_supplied",
        "meter_energy_sum",
        "technical_losses",
        "energy_gap",
        "energy_gap_ratio",
        "meter_count",
    ]
    history_features = history.reindex(columns=feature_columns, fill_value=0.0)
    current_features = current.reindex(columns=feature_columns, fill_value=0.0)
    if len(history_features) < 12 or len(current_features) == 0:
        return np.zeros(len(current_features), dtype=float)

    contamination = float(np.clip(max(history.get("possible_pole_tamper", pd.Series(dtype=float)).mean(), 0.05), 0.05, 0.25))
    model = IsolationForest(n_estimators=120, contamination=contamination, random_state=42)
    model.fit(history_features)
    history_scores = -model.score_samples(history_features)
    current_scores = -model.score_samples(current_features)
    if np.isclose(history_scores.max(), history_scores.min()):
        return np.zeros(len(current_features), dtype=float)
    normalised = (current_scores - history_scores.min()) / (history_scores.max() - history_scores.min())
    return np.clip(normalised, 0.0, 1.0)


def detect_pole_tampering(
    current_frame: pd.DataFrame,
    historical_frame: pd.DataFrame | None = None,
    mismatch_threshold: float = DEFAULT_MISMATCH_THRESHOLD,
    metadata_path: str | Path | None = None,
) -> pd.DataFrame:
    del metadata_path
    current = _ensure_pole_energy_frame(current_frame)
    history = _ensure_pole_energy_frame(historical_frame if historical_frame is not None else current_frame)
    if current.empty:
        return pd.DataFrame(
            columns=[
                "timestamp",
                "transformer_id",
                "pole_id",
                "area",
                "supplied_energy",
                "meter_energy_sum",
                "loss_estimate",
                "energy_gap",
                "tamper_probability",
                "tamper_flag",
            ]
        )

    history_summary = (
        history.groupby("pole_id", as_index=False)
        .agg(
            historical_meter_mean=("meter_energy_sum", "mean"),
            historical_meter_std=("meter_energy_sum", "std"),
            historical_gap_mean=("energy_gap_ratio", "mean"),
            historical_gap_std=("energy_gap_ratio", "std"),
            historical_supply_mean=("energy_supplied", "mean"),
        )
        .fillna(0.0)
    )
    transformer_totals = current.groupby(["timestamp", "transformer_id"], as_index=False).agg(transformer_energy=("energy_supplied", "sum"))
    scored = current.merge(history_summary, on="pole_id", how="left").merge(transformer_totals, on=["timestamp", "transformer_id"], how="left")
    scored = scored.fillna(0.0)

    scored["load_spike_score"] = (
        (scored["meter_energy_sum"] - scored["historical_meter_mean"])
        / scored["historical_meter_std"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    scored["gap_z_score"] = (
        (scored["energy_gap_ratio"] - scored["historical_gap_mean"])
        / scored["historical_gap_std"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    scored["meter_load_ratio"] = (
        scored["meter_energy_sum"] / scored["meter_count"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(scored["meter_energy_sum"])
    scored["transformer_share"] = (
        scored["energy_supplied"] / scored["transformer_energy"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    scored["missing_meter_load"] = np.maximum(scored["energy_gap"] - scored["load_spike_kwh"], 0.0)
    missing_load_ratio = (
        scored["missing_meter_load"] / scored["energy_supplied"].replace(0.0, np.nan)
    ).replace([np.inf, -np.inf], np.nan).fillna(0.0)

    ml_score = _predict_ml_anomaly_score(history, scored)
    heuristic_score = (
        0.38 * np.clip(scored["energy_gap_ratio"] / max(float(mismatch_threshold), 1e-6), 0.0, 1.6)
        + 0.18 * np.clip(scored["load_spike_score"] / 3.5, 0.0, 1.0)
        + 0.18 * np.clip(scored["gap_z_score"] / 3.0, 0.0, 1.0)
        + 0.16 * np.clip(missing_load_ratio, 0.0, 1.0)
        + 0.10 * np.clip(scored["transformer_share"] * 2.5, 0.0, 1.0)
    )
    scored["tamper_probability"] = np.clip(0.7 * heuristic_score + 0.3 * ml_score, 0.0, 0.99).round(4)
    scored["tamper_flag"] = (
        (scored["tamper_probability"] >= 0.72)
        | (scored["energy_gap_ratio"] >= float(mismatch_threshold))
        | (scored["missing_meter_load"] >= scored["technical_losses"] * 1.5)
    ).astype(int)

    scored["supplied_energy"] = scored["energy_supplied"].round(3)
    scored["loss_estimate"] = scored["technical_losses"].round(3)

    result_columns = [
        "timestamp",
        "transformer_id",
        "pole_id",
        "area",
        "meter_count",
        "connected_meters",
        "supplied_energy",
        "meter_energy_sum",
        "loss_estimate",
        "energy_gap",
        "energy_gap_ratio",
        "load_spike_score",
        "missing_meter_load",
        "pole_event_type",
        "tamper_probability",
        "tamper_flag",
    ]
    return scored[result_columns].sort_values(["tamper_flag", "tamper_probability", "energy_gap"], ascending=[False, False, False]).reset_index(drop=True)
