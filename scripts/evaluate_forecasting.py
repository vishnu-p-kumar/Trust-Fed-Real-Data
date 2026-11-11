"""Chronological forecasting benchmark with persistence and seasonal-naive baselines."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd


def _metrics(actual: np.ndarray, predicted: np.ndarray) -> dict[str, float]:
    error = actual - predicted
    denominator = max(float(np.abs(actual).sum()), 1e-9)
    return {"mae": float(np.mean(np.abs(error))), "rmse": float(np.sqrt(np.mean(error ** 2))),
            "wape_pct": float(100 * np.abs(error).sum() / denominator)}


def evaluate(frame: pd.DataFrame, value_column: str = "consumption_kwh", timestamp_column: str = "timestamp", test_fraction: float = .2, seasonal_period: int = 24) -> dict:
    if value_column not in frame or timestamp_column not in frame:
        raise ValueError(f"CSV must contain {timestamp_column!r} and {value_column!r}")
    data = frame[[timestamp_column, value_column]].copy()
    data[timestamp_column] = pd.to_datetime(data[timestamp_column], errors="coerce", utc=True)
    data[value_column] = pd.to_numeric(data[value_column], errors="coerce")
    data = data.dropna().sort_values(timestamp_column).drop_duplicates(timestamp_column, keep="last")
    values = data[value_column].to_numpy(dtype=float)
    if len(values) < max(20, seasonal_period * 2):
        raise ValueError("Not enough observations for chronological baseline evaluation")
    split = int(len(values) * (1 - test_fraction))
    split = min(max(split, seasonal_period), len(values)-1)
    train, test = values[:split], values[split:]
    persistence = np.repeat(train[-1], len(test))
    if len(train) >= seasonal_period:
        seasonal = np.array([train[-seasonal_period + (i % seasonal_period)] for i in range(len(test))])
    else:
        seasonal = np.repeat(float(np.mean(train)), len(test))
    # Expanding mean is a simple leakage-safe baseline: each prediction uses history only.
    expanding = np.array([np.mean(np.concatenate([train, test[:i]])) for i in range(len(test))])
    return {"protocol": "chronological split; no shuffle; test rows excluded from model fitting",
            "observations": len(values), "train_observations": len(train), "test_observations": len(test),
            "split_timestamp_utc": data.iloc[split][timestamp_column].isoformat(),
            "metrics": {"persistence": _metrics(test, persistence), "seasonal_naive": _metrics(test, seasonal),
                        "expanding_mean": _metrics(test, expanding)},
            "warning": "This evaluates baselines only. Compare learned models on the exact same chronological split before claiming improvement."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--value-column", default="consumption_kwh")
    parser.add_argument("--timestamp-column", default="timestamp")
    parser.add_argument("--test-fraction", type=float, default=.2)
    parser.add_argument("--seasonal-period", type=int, default=24)
    parser.add_argument("--output", type=Path, default=Path("reports/research_runs/forecast_baselines.json"))
    args = parser.parse_args()
    result = evaluate(pd.read_csv(args.input, low_memory=False), args.value_column, args.timestamp_column, args.test_fraction, args.seasonal_period)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
