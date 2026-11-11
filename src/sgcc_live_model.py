"""SGCC-trained theft model designed for rolling 30-day live meter histories.

This module deliberately uses consumption-only profile features because SGCC does
not provide synchronized voltage/current telemetry. Incoming live telemetry is
aggregated to daily kWh before scoring.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import (accuracy_score, average_precision_score,
                             f1_score, precision_score, recall_score,
                             roc_auc_score)

from src.federated.partition import stratified_group_holdout

WINDOW_DAYS = 30
MIN_VALID_DAYS = 20
FEATURE_COLUMNS = [
    "mean_kwh", "std_kwh", "median_kwh", "min_kwh", "max_kwh",
    "p10_kwh", "p25_kwh", "p75_kwh", "p90_kwh", "zero_rate",
    "missing_rate", "coefficient_variation", "interquartile_range_kwh",
    "first_third_mean_kwh", "middle_third_mean_kwh", "last_third_mean_kwh",
    "recent_vs_early_delta_kwh", "daily_change_mean_kwh",
    "daily_change_std_kwh", "daily_change_abs_mean_kwh",
    "lag1_autocorrelation", "lag7_autocorrelation", "weekday_mean_kwh",
    "weekend_mean_kwh", "p90_exceedance_rate", "trend_slope_kwh_per_day",
]


def _safe_nanmean(values: np.ndarray, axis: int = 1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(values, axis=axis)


def _safe_nanstd(values: np.ndarray, axis: int = 1) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanstd(values, axis=axis)


def _safe_nanpercentile(values: np.ndarray, q: float) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanpercentile(values, q, axis=1)


def _safe_nanmin(values: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmin(values, axis=1)


def _safe_nanmax(values: np.ndarray) -> np.ndarray:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(values, axis=1)


def _autocorrelation(values: np.ndarray, valid: np.ndarray, lag: int) -> np.ndarray:
    left, right = values[:, :-lag], values[:, lag:]
    pair = valid[:, :-lag] & valid[:, lag:]
    count = np.maximum(pair.sum(axis=1), 2)
    left_mean = np.where(pair, left, 0.0).sum(axis=1) / count
    right_mean = np.where(pair, right, 0.0).sum(axis=1) / count
    left_center = np.where(pair, left - left_mean[:, None], 0.0)
    right_center = np.where(pair, right - right_mean[:, None], 0.0)
    numerator = (left_center * right_center).sum(axis=1)
    denominator = np.sqrt((left_center ** 2).sum(axis=1) * (right_center ** 2).sum(axis=1))
    result = numerator / np.maximum(denominator, 1e-8)
    result[pair.sum(axis=1) < 3] = np.nan
    return result


def extract_window_features(consumption: np.ndarray | list[float], dates: pd.DatetimeIndex | list[Any]) -> pd.DataFrame:
    """Return one feature row for a fixed 30-calendar-day consumption window."""
    x = np.asarray(consumption, dtype=np.float64)
    if x.ndim == 1:
        x = x.reshape(1, -1)
    if x.ndim != 2:
        raise ValueError("Consumption input must be a 1-D window or a 2-D batch of windows.")
    date_index = pd.DatetimeIndex(pd.to_datetime(dates, errors="coerce"))
    if x.shape[1] != WINDOW_DAYS or len(date_index) != WINDOW_DAYS:
        raise ValueError(f"Expected exactly {WINDOW_DAYS} daily readings and dates.")
    x[~np.isfinite(x)] = np.nan
    valid = np.isfinite(x)
    count = np.maximum(valid.sum(axis=1), 1)
    mean = _safe_nanmean(x)
    std = _safe_nanstd(x)
    p10, p25, p75, p90 = (_safe_nanpercentile(x, q) for q in (10, 25, 75, 90))
    first, middle, last = (_safe_nanmean(x[:, sl]) for sl in (slice(0, 10), slice(10, 20), slice(20, 30)))
    diff = np.diff(x, axis=1)
    diff_valid = valid[:, 1:] & valid[:, :-1]
    diff[~diff_valid] = np.nan
    t = np.arange(WINDOW_DAYS, dtype=np.float64)[None, :]
    t_mean = np.where(valid, t, 0.0).sum(axis=1) / count
    x_mean = np.where(valid, x, 0.0).sum(axis=1) / count
    slope_num = np.where(valid, (t - t_mean[:, None]) * (x - x_mean[:, None]), 0.0).sum(axis=1)
    slope_den = np.where(valid, (t - t_mean[:, None]) ** 2, 0.0).sum(axis=1)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        p90_exceed = np.sum((x > p90[:, None]) & valid, axis=1) / count
    weekday_idx = np.asarray(date_index.dayofweek < 5)
    weekend_idx = ~weekday_idx
    weekday = x[:, weekday_idx]
    weekend = x[:, weekend_idx]
    features = {
        "mean_kwh": mean,
        "std_kwh": std,
        "median_kwh": _safe_nanpercentile(x, 50),
        "min_kwh": _safe_nanmin(x),
        "max_kwh": _safe_nanmax(x),
        "p10_kwh": p10,
        "p25_kwh": p25,
        "p75_kwh": p75,
        "p90_kwh": p90,
        "zero_rate": np.sum((x == 0) & valid, axis=1) / count,
        "missing_rate": 1.0 - valid.mean(axis=1),
        "coefficient_variation": std / np.maximum(np.abs(mean), 1e-6),
        "interquartile_range_kwh": p75 - p25,
        "first_third_mean_kwh": first,
        "middle_third_mean_kwh": middle,
        "last_third_mean_kwh": last,
        "recent_vs_early_delta_kwh": last - first,
        "daily_change_mean_kwh": _safe_nanmean(diff),
        "daily_change_std_kwh": _safe_nanstd(diff),
        "daily_change_abs_mean_kwh": _safe_nanmean(np.abs(diff)),
        "lag1_autocorrelation": _autocorrelation(x, valid, 1),
        "lag7_autocorrelation": _autocorrelation(x, valid, 7),
        "weekday_mean_kwh": _safe_nanmean(weekday),
        "weekend_mean_kwh": _safe_nanmean(weekend),
        "p90_exceedance_rate": p90_exceed,
        "trend_slope_kwh_per_day": slope_num / np.maximum(slope_den, 1e-8),
    }
    return pd.DataFrame({name: np.asarray(features[name], dtype=np.float32) for name in FEATURE_COLUMNS})


def build_sgcc_window_dataset(raw_path: str | Path, windows_per_customer: int = 1) -> tuple[pd.DataFrame, pd.Series, pd.Series, dict[str, Any]]:
    """Build fixed-window samples; group IDs preserve customer-disjoint splits."""
    source = Path(raw_path)
    header = pd.read_csv(source, nrows=0).columns.tolist()
    header_map = {str(column).strip().lower(): column for column in header}
    id_hint = header_map.get("cons_no") or header_map.get("consno")
    label_hint = header_map.get("flag")
    if id_hint is None or label_hint is None:
        raise ValueError("SGCC source must contain CONS_NO and FLAG columns.")
    daily_hints = []
    for column in header:
        if column in {id_hint, label_hint}:
            continue
        if pd.notna(pd.to_datetime(str(column), format="%Y/%m/%d", errors="coerce")):
            daily_hints.append(column)
    dtype_map = {column: np.float32 for column in daily_hints}
    dtype_map[id_hint] = str
    dtype_map[label_hint] = np.int8
    raw = pd.read_csv(source, low_memory=False, dtype=dtype_map)
    column_map = {str(column).strip().lower(): column for column in raw.columns}
    id_col = column_map.get("cons_no") or column_map.get("consno")
    label_col = column_map.get("flag")
    if id_col is None or label_col is None:
        raise ValueError("SGCC source must contain CONS_NO and FLAG columns.")
    parsed_dates = []
    for column in raw.columns:
        if column in {id_col, label_col}:
            continue
        parsed = pd.to_datetime(str(column), format="%Y/%m/%d", errors="coerce")
        if pd.notna(parsed):
            parsed_dates.append((parsed, column))
    parsed_dates.sort(key=lambda item: item[0])
    if len(parsed_dates) < WINDOW_DAYS:
        raise ValueError("SGCC source does not have enough daily columns for a 30-day window.")
    labels = pd.to_numeric(raw[label_col], errors="coerce")
    if labels.isna().any() or labels.nunique() != 2 or not set(labels.unique()).issubset({0, 1}):
        raise ValueError("SGCC FLAG must contain both binary classes 0 and 1.")
    groups = raw[id_col].astype(str)
    if groups.isna().any() or groups.duplicated().any():
        raise ValueError("SGCC customer IDs must be unique and non-null.")
    date_index = pd.DatetimeIndex([item[0] for item in parsed_dates])
    values = raw[[item[1] for item in parsed_dates]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype=np.float32)
    n_days = values.shape[1]
    if windows_per_customer == 1:
        rng = np.random.default_rng(20261101)
        starts_by_customer = rng.integers(0, n_days - WINDOW_DAYS + 1, size=len(raw))
        feature_values = np.empty((len(raw), len(FEATURE_COLUMNS)), dtype=np.float32)
        for start in np.unique(starts_by_customer):
            row_indices = np.flatnonzero(starts_by_customer == start)
            feature_values[row_indices] = extract_window_features(
                values[row_indices, start:start + WINDOW_DAYS],
                date_index[start:start + WINDOW_DAYS],
            ).to_numpy(dtype=np.float32)
        feature_frames = [pd.DataFrame(feature_values, columns=FEATURE_COLUMNS)]
        group_parts = [groups.to_numpy()]
        label_parts = [labels.to_numpy(dtype=np.int8)]
    else:
        starts = np.unique(np.linspace(0, n_days - WINDOW_DAYS, num=max(1, windows_per_customer), dtype=int))
        feature_frames = []
        group_parts = []
        label_parts = []
        for start in starts:
            feature_frames.append(extract_window_features(values[:, start:start + WINDOW_DAYS], date_index[start:start + WINDOW_DAYS]))
            group_parts.append(groups.to_numpy())
            label_parts.append(labels.to_numpy(dtype=np.int8))
    X = pd.concat(feature_frames, ignore_index=True)[FEATURE_COLUMNS]
    group_array = np.concatenate(group_parts)
    y = pd.Series(np.concatenate(label_parts), name="is_theft", dtype=np.int8)
    window_count = 1 if windows_per_customer == 1 else int(len(starts))
    meta = {
        "dataset": "SGCC labelled electricity-theft benchmark",
        "source_file": source.name,
        "customer_count": int(groups.nunique()),
        "window_days": WINDOW_DAYS,
        "windows_per_customer": window_count,
        "training_window_count": int(len(X)),
        "feature_count": len(FEATURE_COLUMNS),
        "date_start": str(date_index.min().date()),
        "date_end": str(date_index.max().date()),
        "label_counts": {"0": int((labels == 0).sum()), "1": int((labels == 1).sum())},
        "positive_label_scope": "Published SGCC FLAG benchmark labels; no individual inspection records are bundled.",
        "live_input_contract": "Daily interval energy consumption (kWh) aggregated per meter; 30 calendar days required; at least 20 valid days recommended.",
        "feature_columns": FEATURE_COLUMNS,
        "limitations": ["Historical Chinese utility benchmark", "Does not include synchronized voltage/current inputs", "Live Indian utility performance requires independent labelled validation"],
    }
    return X, y, pd.Series(group_array, name="meter_id"), meta


def choose_recall_threshold(y_true: np.ndarray, probabilities: np.ndarray, target_recall: float = 0.40) -> float:
    from sklearn.metrics import precision_recall_curve
    precision, recall, thresholds = precision_recall_curve(y_true, probabilities)
    if thresholds.size == 0:
        return 0.5
    eligible = np.flatnonzero(recall[:-1] >= target_recall)
    if eligible.size == 0:
        return float(np.quantile(probabilities, 0.5))
    best_precision = precision[eligible].max()
    best = eligible[np.flatnonzero(precision[eligible] == best_precision)[-1]]
    return float(thresholds[best])


def _aggregate_customer_scores(y: np.ndarray, probabilities: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    frame = pd.DataFrame({"y": y, "probability": probabilities, "group": groups.astype(str)})
    grouped = frame.groupby("group", sort=False).agg(y=("y", "max"), probability=("probability", "mean")).reset_index()
    return grouped["y"].to_numpy(dtype=int), grouped["probability"].to_numpy(dtype=float), grouped["group"].to_numpy()


def train_sgcc_live_model(raw_path: str | Path, model_path: str | Path, metadata_path: str | Path,
                          seed: int = 42, target_recall: float = 0.40,
                          windows_per_customer: int = 1) -> dict[str, Any]:
    from sklearn.metrics import confusion_matrix
    X, y, groups, meta = build_sgcc_window_dataset(raw_path, windows_per_customer=windows_per_customer)
    trainval_idx, test_idx = stratified_group_holdout(y.to_numpy(), groups.to_numpy(), test_size=0.20, seed=seed)
    train_rel, val_rel = stratified_group_holdout(y.iloc[trainval_idx].to_numpy(), groups.iloc[trainval_idx].to_numpy(), test_size=0.1875, seed=seed + 1)
    train_idx = trainval_idx[train_rel]
    val_idx = trainval_idx[val_rel]
    model = HistGradientBoostingClassifier(
        learning_rate=0.08,
        max_iter=90,
        max_leaf_nodes=15,
        l2_regularization=1.5,
        random_state=seed,
        early_stopping=True,
        validation_fraction=0.1,
        n_iter_no_change=15,
    )
    model.fit(X.iloc[train_idx], y.iloc[train_idx])
    val_probs_rows = model.predict_proba(X.iloc[val_idx])[:, 1]
    y_val, p_val, _ = _aggregate_customer_scores(y.iloc[val_idx].to_numpy(), val_probs_rows, groups.iloc[val_idx].to_numpy())
    threshold = choose_recall_threshold(y_val, p_val, target_recall=target_recall)
    test_probs_rows = model.predict_proba(X.iloc[test_idx])[:, 1]
    y_test, p_test, test_groups = _aggregate_customer_scores(y.iloc[test_idx].to_numpy(), test_probs_rows, groups.iloc[test_idx].to_numpy())
    predicted = (p_test >= threshold).astype(int)
    cm = confusion_matrix(y_test, predicted, labels=[0, 1]).tolist()
    metrics = {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision": float(precision_score(y_test, predicted, zero_division=0)),
        "recall": float(recall_score(y_test, predicted, zero_division=0)),
        "f1": float(f1_score(y_test, predicted, zero_division=0)),
        "pr_auc": float(average_precision_score(y_test, p_test)),
        "roc_auc": float(roc_auc_score(y_test, p_test)) if np.unique(y_test).size > 1 else None,
        "test_customer_count": int(len(y_test)),
        "confusion_matrix_tn_fp_fn_tp": cm,
        "validation_customer_count": int(len(y_val)),
        "training_window_rows": int(len(train_idx)),
        "test_window_rows": int(len(test_idx)),
    }
    metadata = {
        **meta,
        "model_name": "HistGradientBoostingClassifier",
        "model_source": "SGCC only; no synthetic training data",
        "seed": seed,
        "target_validation_recall": target_recall,
        "selected_threshold": threshold,
        "validation_metrics_at_threshold": {
            "precision": float(precision_score(y_val, (p_val >= threshold).astype(int), zero_division=0)),
            "recall": float(recall_score(y_val, (p_val >= threshold).astype(int), zero_division=0)),
        },
        "test_metrics_customer_aggregated": metrics,
        "split_protocol": "customer-disjoint train/validation/test; all windows from a customer remain in one partition; test untouched for threshold selection",
        "minimum_valid_days": MIN_VALID_DAYS,
        "status_notice": "The output is a suspicion score for investigation, not proof of electricity theft.",
    }
    model_file = Path(model_path)
    metadata_file = Path(metadata_path)
    model_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_file)
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return {"model_path": str(model_file), "metadata_path": str(metadata_file), "metrics": metrics,
            "threshold": threshold, "metadata": metadata}


class SGCCLiveTheftDetector:
    def __init__(self, model_path: str | Path, metadata_path: str | Path):
        self.model_path = Path(model_path)
        self.metadata_path = Path(metadata_path)
        if not self.model_path.exists() or not self.metadata_path.exists():
            raise FileNotFoundError("SGCC live model artifacts are missing; run scripts/train_sgcc_live_model.py first.")
        self.model = joblib.load(self.model_path)
        self.metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        if self.metadata.get("model_source") != "SGCC only; no synthetic training data":
            raise ValueError("Refusing to load a model without SGCC-only training provenance.")
        self.threshold = float(self.metadata["selected_threshold"])
        self.minimum_valid_days = int(self.metadata.get("minimum_valid_days", MIN_VALID_DAYS))

    def score_daily_history(self, daily: pd.Series) -> dict[str, Any]:
        """Score one meter's daily kWh history, returning warm-up state if not ready."""
        series = pd.to_numeric(daily, errors="coerce").copy()
        series.index = pd.to_datetime(series.index).normalize()
        series = series.groupby(level=0).sum(min_count=1).sort_index()
        if series.empty:
            return {"ready": False, "status": "Insufficient History", "valid_days": 0,
                    "required_valid_days": self.minimum_valid_days, "history_days": 0}
        end = series.index.max()
        index = pd.date_range(end=end, periods=WINDOW_DAYS, freq="D")
        window = series.reindex(index)
        valid_days = int(window.notna().sum())
        history_days = int((series.index.max() - series.index.min()).days + 1)
        if history_days < WINDOW_DAYS or valid_days < self.minimum_valid_days:
            return {"ready": False, "status": "Insufficient History", "valid_days": valid_days,
                    "required_valid_days": self.minimum_valid_days, "history_days": history_days,
                    "required_history_days": WINDOW_DAYS}
        features = extract_window_features(window.to_numpy(dtype=float), index)[FEATURE_COLUMNS]
        probability = float(self.model.predict_proba(features)[:, 1][0])
        suspected = probability >= self.threshold
        return {"ready": True, "status": "Electricity Theft" if suspected else "Normal",
                "theft_probability": probability, "threshold": self.threshold,
                "valid_days": valid_days, "history_days": history_days,
                "required_history_days": WINDOW_DAYS,
                "model_source": "SGCC labelled benchmark", "feature_count": len(FEATURE_COLUMNS)}
