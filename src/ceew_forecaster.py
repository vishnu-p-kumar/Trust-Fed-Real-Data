"""CEEW-trained next-day consumption forecasting (never used for theft labels)."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

FEATURES = [*[f"lag_{i}" for i in range(1, 8)], "mean_7", "std_7", "weekday_sin", "weekday_cos"]


def _features(history: pd.Series, target_date: pd.Timestamp) -> pd.DataFrame:
    values = pd.to_numeric(history, errors="coerce").dropna().tail(7).to_numpy(dtype=float)
    if len(values) < 7:
        raise ValueError("At least seven valid daily consumption values are required for forecasting.")
    day = pd.Timestamp(target_date).dayofweek
    row = {f"lag_{i}": float(values[-i]) for i in range(1, 8)}
    row.update({"mean_7": float(values.mean()), "std_7": float(values.std(ddof=0)),
                "weekday_sin": float(np.sin(2*np.pi*day/7)),
                "weekday_cos": float(np.cos(2*np.pi*day/7))})
    return pd.DataFrame([row], columns=FEATURES)


def _load_daily_sources(paths: list[str | Path]) -> pd.DataFrame:
    frames = []
    for path in paths:
        source = Path(path)
        if not source.exists():
            continue
        frame = pd.read_csv(source)
        required = {"meter", "Date", "t_kWh"}
        if not required.issubset(frame.columns):
            raise ValueError(f"CEEW daily file {source.name} must contain {sorted(required)}")
        normalized = frame.rename(columns={"meter": "meter_id", "Date": "timestamp", "t_kWh": "consumption_kwh"})
        normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], errors="coerce")
        normalized["consumption_kwh"] = pd.to_numeric(normalized["consumption_kwh"], errors="coerce")
        normalized = normalized.dropna(subset=["meter_id", "timestamp", "consumption_kwh"])
        normalized = normalized.loc[normalized["consumption_kwh"] >= 0]
        frames.append(normalized[["meter_id", "timestamp", "consumption_kwh"]])
    if not frames:
        raise FileNotFoundError("No CEEW daily aggregate files found for forecasting.")
    return pd.concat(frames, ignore_index=True).drop_duplicates(["meter_id", "timestamp"], keep="last")


def _build_examples(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for meter_id, meter in frame.groupby("meter_id"):
        meter = meter.sort_values("timestamp").set_index("timestamp")["consumption_kwh"]
        daily = meter.resample("D").sum(min_count=1)
        # Reset lag history after long gaps; missing dates must not be treated as zero.
        for target_idx in range(7, len(daily)):
            window = daily.iloc[target_idx-7:target_idx]
            target = daily.iloc[target_idx]
            if window.notna().all() and pd.notna(target):
                feat = _features(window, daily.index[target_idx]).iloc[0].to_dict()
                feat.update({"meter_id": str(meter_id), "timestamp": daily.index[target_idx], "target": float(target)})
                rows.append(feat)
    return pd.DataFrame(rows)


def train_ceew_forecaster(source_paths: list[str | Path], model_path: str | Path, metadata_path: str | Path) -> dict[str, Any]:
    raw = _load_daily_sources(source_paths)
    examples = _build_examples(raw)
    if len(examples) < 100:
        raise ValueError("CEEW daily dataset produced fewer than 100 forecasting examples.")
    train_parts, validation_parts, test_parts = [], [], []
    for _, meter in examples.groupby("meter_id"):
        meter = meter.sort_values("timestamp")
        n = len(meter)
        if n < 12:
            train_parts.append(meter)
            continue
        train_end = max(7, int(n * .60))
        val_end = max(train_end + 1, int(n * .80))
        train_parts.append(meter.iloc[:train_end])
        validation_parts.append(meter.iloc[train_end:val_end])
        test_parts.append(meter.iloc[val_end:])
    train = pd.concat(train_parts, ignore_index=True)
    validation = pd.concat(validation_parts, ignore_index=True) if validation_parts else pd.DataFrame()
    test = pd.concat(test_parts, ignore_index=True) if test_parts else pd.DataFrame()
    if validation.empty or test.empty:
        raise ValueError("CEEW data needs longer per-meter histories for chronological validation and test splits.")
    model = HistGradientBoostingRegressor(learning_rate=.06, max_iter=120, max_leaf_nodes=15,
                                          l2_regularization=1.0, random_state=42, early_stopping=True)
    model.fit(train[FEATURES], train["target"])
    learned_val = np.maximum(0.0, model.predict(validation[FEATURES]))
    persistence_val = validation["lag_1"].to_numpy(dtype=float)
    learned_mae_val = float(mean_absolute_error(validation["target"], learned_val))
    persistence_mae_val = float(mean_absolute_error(validation["target"], persistence_val))
    selected = "ceew_hist_gradient_boosting" if learned_mae_val < persistence_mae_val else "persistence_baseline"
    learned_test = np.maximum(0.0, model.predict(test[FEATURES]))
    persistence_test = test["lag_1"].to_numpy(dtype=float)
    test_metrics = {
        "learned_model_mae_kwh": float(mean_absolute_error(test["target"], learned_test)),
        "persistence_mae_kwh": float(mean_absolute_error(test["target"], persistence_test)),
        "learned_model_rmse_kwh": float(mean_squared_error(test["target"], learned_test) ** .5),
        "persistence_rmse_kwh": float(mean_squared_error(test["target"], persistence_test) ** .5),
        "test_examples": int(len(test)),
    }
    model_file, metadata_file = Path(model_path), Path(metadata_path)
    model_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, model_file)
    metadata = {
        "dataset": "CEEW Mathura and Bareilly daily smart-meter aggregates",
        "task": "next-day consumption forecasting; not theft detection",
        "selected_forecaster": selected,
        "selection_rule": "learned model selected only when validation MAE beats persistence baseline",
        "validation_mae_kwh": {"learned_model": learned_mae_val, "persistence": persistence_mae_val},
        "test_metrics": test_metrics,
        "training_examples": int(len(train)), "validation_examples": int(len(validation)),
        "meter_count": int(raw["meter_id"].nunique()), "features": FEATURES,
        "theft_labels_used": False,
        "limitations": ["CEEW has no verified theft labels", "forecasting residuals are not proof of theft"],
    }
    metadata_file.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


class CEEWConsumptionForecaster:
    def __init__(self, model_path: str | Path, metadata_path: str | Path):
        self.model = joblib.load(model_path)
        self.metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
        self.selected_forecaster = self.metadata["selected_forecaster"]

    def forecast_next_day(self, daily_history: pd.Series) -> dict[str, Any]:
        history = pd.to_numeric(daily_history, errors="coerce").sort_index()
        valid = history.dropna().tail(7)
        if len(valid) < 7:
            return {"ready": False, "reason": "Seven valid daily readings are required for CEEW-based forecasting."}
        target_date = pd.Timestamp(valid.index.max()) + pd.Timedelta(days=1)
        if self.selected_forecaster == "persistence_baseline":
            prediction = float(valid.iloc[-1])
        else:
            prediction = float(max(0.0, self.model.predict(_features(valid, target_date)[FEATURES])[0]))
        return {"ready": True, "forecast_date": target_date.isoformat(),
                "predicted_consumption_kwh": prediction,
                "forecaster": self.selected_forecaster,
                "training_dataset": "CEEW Mathura and Bareilly daily aggregates"}
