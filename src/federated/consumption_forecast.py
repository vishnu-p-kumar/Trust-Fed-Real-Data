"""Meter-disjoint federated next-reading forecasts for unlabeled CEEW data."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.federated.aggregators import fedavg, trimmed_mean
from src.federated.partition import partition_by_group


def _build_examples(frame: pd.DataFrame, interval: pd.Timedelta) -> tuple[pd.DataFrame, dict[str, int]]:
    required = {"meter_id", "timestamp", "consumption_kwh"}
    if not required.issubset(frame.columns):
        raise ValueError(f"consumption forecast requires columns: {sorted(required)}")
    if interval <= pd.Timedelta(0):
        raise ValueError("interval must be positive")
    source_columns = ["meter_id", "timestamp", "consumption_kwh"] + (["location"] if "location" in frame else [])
    raw = frame.loc[:, source_columns].copy()
    raw["meter_id"] = raw["meter_id"].astype("string").str.strip()
    raw["timestamp"] = pd.to_datetime(raw["timestamp"], errors="coerce")
    raw["consumption_kwh"] = pd.to_numeric(raw["consumption_kwh"], errors="coerce")
    valid = (raw["meter_id"].notna() & raw["meter_id"].ne("") & raw["timestamp"].notna()
             & raw["consumption_kwh"].notna() & np.isfinite(raw["consumption_kwh"])
             & raw["consumption_kwh"].ge(0))
    dropped_invalid = int((~valid).sum())
    raw = raw.loc[valid].sort_values(["meter_id", "timestamp"], kind="mergesort")
    meter_locations: dict[str, str] = {}
    if "location" in raw:
        location_counts = raw.groupby("meter_id")["location"].nunique(dropna=True)
        if (location_counts > 1).any():
            raise ValueError("a meter cannot be assigned to multiple locations")
        meter_locations = raw.groupby("meter_id")["location"].first().astype(str).to_dict()
    duplicate_mask = raw.duplicated(["meter_id", "timestamp"], keep="last")
    duplicate_rows = int(duplicate_mask.sum())
    raw = raw.loc[~duplicate_mask]

    pieces = []
    offset = interval * 7
    for meter, group in raw.groupby("meter_id", sort=True):
        series = group.set_index("timestamp")["consumption_kwh"].sort_index()
        current_times = series.index
        previous = series.reindex(current_times - interval).to_numpy(dtype=float)
        previous_week = series.reindex(current_times - offset).to_numpy(dtype=float)
        future = series.reindex(current_times + interval).to_numpy(dtype=float)
        valid_example = np.isfinite(previous) & np.isfinite(previous_week) & np.isfinite(future)
        if not valid_example.any():
            continue
        targets_at = current_times[valid_example] + interval
        frame_part = pd.DataFrame({
            "meter_id": str(meter),
            "target_timestamp": targets_at,
            "x_lag1": np.log1p(previous[valid_example]),
            "x_lag7": np.log1p(previous_week[valid_example]),
            "x_weekday_sin": np.sin(2 * np.pi * targets_at.dayofweek / 7),
            "x_weekday_cos": np.cos(2 * np.pi * targets_at.dayofweek / 7),
            "x_day_sin": np.sin(2 * np.pi * (targets_at.hour * 60 + targets_at.minute) / 1440),
            "x_day_cos": np.cos(2 * np.pi * (targets_at.hour * 60 + targets_at.minute) / 1440),
            "target_log_kwh": np.log1p(future[valid_example]),
            "target_kwh": future[valid_example],
        })
        if meter_locations:
            frame_part["location"] = meter_locations[str(meter)]
        pieces.append(frame_part)
    if not pieces:
        raise ValueError("not enough regular history to form one-step and seven-day lag examples")
    examples = pd.concat(pieces, ignore_index=True)
    # Split each meter chronologically by target timestamp; the feature window
    # may use historical observations before a split boundary, as deployment does.
    examples["split"] = "train"
    for _, group in examples.groupby("meter_id", sort=False):
        ordered = group.sort_values("target_timestamp").index
        n = len(ordered)
        train_end = max(1, int(np.floor(n * .6)))
        val_end = max(train_end + 1, int(np.floor(n * .8)))
        val_end = min(val_end, n - 1) if n >= 3 else n
        examples.loc[ordered[train_end:val_end], "split"] = "validation"
        examples.loc[ordered[val_end:], "split"] = "test"
    return examples, {"invalid_rows_excluded": dropped_invalid, "duplicate_key_rows_excluded": duplicate_rows}


def _fit_linear(x: np.ndarray, y: np.ndarray, initial: np.ndarray, epochs: int, learning_rate: float) -> np.ndarray:
    weights = initial.copy()
    if len(y) == 0:
        raise ValueError("each participating client must have training examples")
    design = np.column_stack([x, np.ones(len(x))])
    for _ in range(epochs):
        error = design @ weights - y
        gradient = design.T @ error / len(y)
        weights -= learning_rate * gradient
    if not np.isfinite(weights).all():
        raise ValueError("non-finite regression weights; reduce learning_rate")
    return weights


def _metrics(y: np.ndarray, pred: np.ndarray) -> dict[str, float | int]:
    if len(y) == 0:
        return {"n": 0, "mae_kwh": float("nan"), "rmse_kwh": float("nan"), "wape": float("nan")}
    errors = pred - y
    return {"n": int(len(y)), "mae_kwh": float(np.mean(np.abs(errors))),
            "rmse_kwh": float(np.sqrt(np.mean(errors ** 2))),
            "wape": float(np.sum(np.abs(errors)) / max(float(np.sum(np.abs(y))), 1e-12))}


def run_consumption_forecast(
    frame: pd.DataFrame,
    *,
    clients: int = 4,
    rounds: int = 3,
    local_epochs: int = 5,
    learning_rate: float = .02,
    learning_rate_candidates: list[float] | None = None,
    seed: int = 42,
    interval: str = "1D",
    client_partition: str = "meter_groups",
) -> dict[str, Any]:
    """Run chronological, meter-partitioned forecasting; no theft label is used."""
    if rounds < 1 or local_epochs < 1 or learning_rate <= 0:
        raise ValueError("rounds, local_epochs, and learning_rate must be positive")
    examples, quality = _build_examples(frame, pd.Timedelta(interval))
    split_counts = examples["split"].value_counts()
    if any(int(split_counts.get(name, 0)) == 0 for name in ("train", "validation", "test")):
        raise ValueError("each chronological train/validation/test split must contain forecast examples")
    if examples["meter_id"].nunique() < clients:
        raise ValueError("client count exceeds meters with usable forecast examples")
    if client_partition not in {"meter_groups", "location"}:
        raise ValueError("client_partition must be meter_groups or location")
    if client_partition == "location":
        if "location" not in examples:
            raise ValueError("location partition requires a location column")
        group_values = examples["location"].to_numpy()
    else:
        group_values = examples["meter_id"].to_numpy()
    partitions = partition_by_group(group_values, clients=clients, seed=seed)
    x_columns = [col for col in examples.columns if col.startswith("x_")]
    client_rows = {part.client_id: examples.iloc[part.indices].copy() for part in partitions}
    for client_id, part in client_rows.items():
        if part["split"].eq("train").sum() == 0 or part["split"].eq("test").sum() == 0:
            raise ValueError(f"{client_id} has no chronological train or test examples")

    initial = np.zeros(len(x_columns) + 1, dtype=float)

    def fit_fedavg(rate: float) -> tuple[np.ndarray, int]:
        weights = initial.copy()
        transmitted = 0
        for _ in range(rounds):
            deltas, sizes = [], []
            for part in client_rows.values():
                train = part.loc[part["split"].eq("train")]
                local = _fit_linear(train[x_columns].to_numpy(dtype=float),
                                    train["target_log_kwh"].to_numpy(dtype=float),
                                    weights, local_epochs, rate)
                deltas.append(local - weights)
                sizes.append(len(train))
            weights += fedavg(deltas, sizes)
            transmitted += len(deltas) * weights.nbytes * 2
        return weights, transmitted

    candidates = list(dict.fromkeys(learning_rate_candidates or [learning_rate]))
    if not candidates or any(not np.isfinite(rate) or rate <= 0 for rate in candidates):
        raise ValueError("learning-rate candidates must be positive and finite")
    val = examples.loc[examples["split"].eq("validation")]
    val_design = np.column_stack([val[x_columns].to_numpy(dtype=float), np.ones(len(val))])
    val_actual = val["target_kwh"].to_numpy(dtype=float)
    candidate_results = []
    for rate in candidates:
        candidate_weights, _ = fit_fedavg(float(rate))
        val_prediction = np.maximum(0, np.expm1(np.clip(val_design @ candidate_weights, -30, 30)))
        candidate_results.append((float(rate), float(np.mean(np.abs(val_prediction - val_actual))), candidate_weights))
    selected_rate, _, global_weights = min(candidate_results, key=lambda row: row[1])
    learning_rate = selected_rate
    communication_bytes = len(client_rows) * global_weights.nbytes * 2 * rounds

    # Same local update schedule for coordinate trimmed mean, initialized at 0.
    robust_weights = initial.copy()
    for _ in range(rounds):
        deltas, sizes = [], []
        for part in client_rows.values():
            train = part.loc[part["split"].eq("train")]
            local = _fit_linear(train[x_columns].to_numpy(dtype=float),
                                train["target_log_kwh"].to_numpy(dtype=float), robust_weights,
                                local_epochs, learning_rate)
            deltas.append(local - robust_weights)
            sizes.append(len(train))
        robust_weights += trimmed_mean(deltas, trim_fraction=.1)

    train_all = examples.loc[examples["split"].eq("train")]
    central_weights = _fit_linear(train_all[x_columns].to_numpy(dtype=float),
                                  train_all["target_log_kwh"].to_numpy(dtype=float),
                                  initial, rounds * local_epochs, learning_rate)
    local_weights = {}
    for client_id, part in client_rows.items():
        train = part.loc[part["split"].eq("train")]
        local_weights[client_id] = _fit_linear(train[x_columns].to_numpy(dtype=float),
                                               train["target_log_kwh"].to_numpy(dtype=float),
                                               initial, rounds * local_epochs, learning_rate)

    method_weights = {"centralized": central_weights, "fedavg": global_weights,
                      "trimmed_mean": robust_weights}
    method_metrics: dict[str, dict[str, dict[str, float | int]]] = {}
    validation_residuals: list[np.ndarray] = []
    test_residuals: list[np.ndarray] = []
    for split_name in ("validation", "test"):
        split_rows = examples.loc[examples["split"].eq(split_name)]
        x_split = split_rows[x_columns].to_numpy(dtype=float)
        y_split = split_rows["target_kwh"].to_numpy(dtype=float)
        design = np.column_stack([x_split, np.ones(len(x_split))])
        split_metrics = {}
        for name, weights in method_weights.items():
            pred = np.maximum(0, np.expm1(np.clip(design @ weights, -30, 30)))
            split_metrics[name] = _metrics(y_split, pred)
            if name == "fedavg":
                residual = np.abs(pred - y_split)
                (validation_residuals if split_name == "validation" else test_residuals).append(residual)
        local_predictions, local_actual = [], []
        for client_id, part in client_rows.items():
            client_split = part.loc[part["split"].eq(split_name)]
            if client_split.empty:
                continue
            local_design = np.column_stack([client_split[x_columns].to_numpy(dtype=float), np.ones(len(client_split))])
            local_predictions.extend(np.maximum(0, np.expm1(np.clip(local_design @ local_weights[client_id], -30, 30))).tolist())
            local_actual.extend(client_split["target_kwh"].tolist())
        split_metrics["local_only"] = _metrics(np.asarray(local_actual), np.asarray(local_predictions))
        persistence = np.maximum(0, np.expm1(split_rows["x_lag1"].to_numpy(dtype=float)))
        split_metrics["persistence"] = _metrics(y_split, persistence)
        method_metrics[split_name] = split_metrics

    val_error = np.concatenate(validation_residuals) if validation_residuals else np.asarray([])
    test_error = np.concatenate(test_residuals) if test_residuals else np.asarray([])
    anomaly_threshold = float(np.quantile(val_error, .99)) if len(val_error) else None

    client_to_rows = {client_id: int(len(part)) for client_id, part in client_rows.items()}
    return {
        "task": "next-interval consumption forecast; not theft detection",
        "label_status": "no verified theft labels; no theft labels were created or used",
        "config": {"clients": clients, "rounds": rounds, "local_epochs": local_epochs,
                   "learning_rate": learning_rate, "seed": seed, "interval": str(pd.Timedelta(interval)),
                   "client_partition": "whole meter groups assigned once; deterministic seed" if client_partition == "meter_groups" else "whole locations assigned once (non-IID geographic split)",
                   "split": "per-meter chronological 60/20/20 by forecast target timestamp",
                   "features": x_columns, "preprocessing": "fixed log1p consumption transform and calendar sine/cosine; no fitted feature transforms"},
        "hyperparameter_selection": {"selected_learning_rate": learning_rate,
                                     "selection_metric": "FedAvg validation MAE in kWh",
                                     "validation_candidates": [{"learning_rate": rate, "validation_mae_kwh": score}
                                                                for rate, score, _ in candidate_results]},
        "quality": quality,
        "counts": {"meters": int(examples["meter_id"].nunique()), "examples": int(len(examples)),
                   **{key: int(value) for key, value in examples["split"].value_counts().items()}},
        "client_row_counts": client_to_rows,
        "metrics": method_metrics,
        "forecast_residual_anomaly_proxy": {
            "definition": "absolute next-interval forecast residual; not a theft label or validated theft detector",
            "threshold_quantile_selected_on_validation": .99,
            "threshold_kwh": anomaly_threshold,
            "test_rows_above_threshold": int((test_error > anomaly_threshold).sum()) if anomaly_threshold is not None else None,
            "test_rows": int(len(test_error)),
        },
        "communication_bytes_estimate_fedavg": int(communication_bytes),
        "privacy": "single-process simulation; no DP or secure aggregation",
    }
