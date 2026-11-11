from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from utils.helpers import ensure_project_dirs, load_json, save_json

try:  # pragma: no cover - optional at runtime
    import tensorflow as tf
    from tensorflow.keras import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout
except Exception:  # pragma: no cover - optional at runtime
    tf = None
    Sequential = None
    LSTM = None
    Dense = None
    Dropout = None


def build_demand_series(dataframe: pd.DataFrame) -> pd.DataFrame:
    if dataframe.empty:
        return pd.DataFrame(columns=["timestamp", "consumption_kwh"])
    return (
        dataframe.groupby("timestamp", as_index=False)
        .agg(consumption_kwh=("consumption_kwh", "sum"))
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def _create_sequences(values: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    features, targets = [], []
    for index in range(lookback, len(values)):
        features.append(values[index - lookback : index])
        targets.append(values[index])
    return np.asarray(features), np.asarray(targets)


def _build_lstm_model(lookback: int) -> Sequential:
    model = Sequential(
        [
            LSTM(64, return_sequences=True, input_shape=(lookback, 1)),
            Dropout(0.2),
            LSTM(32),
            Dense(16, activation="relu"),
            Dense(1),
        ]
    )
    model.compile(optimizer="adam", loss="mse")
    return model


def train_lstm_forecaster(
    dataframe: pd.DataFrame,
    lookback: int = 24,
    epochs: int = 5,
    batch_size: int = 64,
    model_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    model_path = Path(model_path) if model_path else paths.lstm_model
    metadata_path = Path(metadata_path) if metadata_path else paths.demand_metadata

    series = build_demand_series(dataframe)
    if series.empty or len(series) <= lookback + 8:
        metadata = {"model_type": "baseline", "lookback": lookback, "history_values": [], "timestamps": []}
        save_json(metadata, metadata_path)
        return metadata

    values = series["consumption_kwh"].astype(float).to_numpy()
    # Fit the scaler only on the chronological training segment. Fitting on the full
    # series leaks the future range into training and produces optimistic evaluation.
    split_index = min(max(int(len(values) * 0.8), lookback + 1), len(values) - 1)
    scaler = MinMaxScaler()
    scaler.fit(values[:split_index].reshape(-1, 1))
    scaled = scaler.transform(values.reshape(-1, 1)).flatten()
    features, targets = _create_sequences(scaled, lookback=lookback)
    features = features.reshape((-1, lookback, 1))
    target_indices = np.arange(lookback, len(values))
    train_mask = target_indices < split_index
    validation_mask = target_indices >= split_index
    train_features, train_targets = features[train_mask], targets[train_mask]
    validation_features, validation_targets = features[validation_mask], targets[validation_mask]

    metadata: dict[str, Any] = {
        "lookback": lookback,
        "timestamps": [timestamp.isoformat() for timestamp in series["timestamp"].tail(168)],
        "history_values": values[-168:].round(3).tolist(),
        "scaler_min": float(scaler.data_min_[0]),
        "scaler_max": float(scaler.data_max_[0]),
        "last_window": scaled[-lookback:].round(6).tolist(),
    }

    if tf is None or len(train_features) < 64 or len(validation_features) < 8:
        metadata["model_type"] = "baseline"
        metadata["training_protocol"] = "chronological 80/20 split; scaler fit on training segment only"
        save_json(metadata, metadata_path)
        return metadata

    model = _build_lstm_model(lookback)
    model.fit(
        train_features, train_targets, epochs=epochs, batch_size=batch_size, verbose=0,
        validation_data=(validation_features, validation_targets), shuffle=False,
    )
    model.save(model_path, include_optimizer=False)
    metadata["model_type"] = "lstm"
    metadata["training_protocol"] = "chronological 80/20 split; scaler fit on training segment only; shuffle disabled"
    metadata["train_observations"] = int(split_index)
    metadata["validation_observations"] = int(len(values) - split_index)
    save_json(metadata, metadata_path)
    return metadata


def _inverse_scale(values: np.ndarray, metadata: dict[str, Any]) -> np.ndarray:
    minimum = metadata.get("scaler_min", 0.0)
    maximum = metadata.get("scaler_max", 1.0)
    if maximum == minimum:
        return np.full_like(values, fill_value=minimum, dtype=float)
    return values * (maximum - minimum) + minimum


def _baseline_forecast(history_values: list[float], horizon: int) -> np.ndarray:
    history = np.asarray(history_values, dtype=float)
    if history.size == 0:
        return np.zeros(horizon, dtype=float)
    if history.size < 24:
        return np.full(horizon, history.mean(), dtype=float)

    window = history[-24:].copy()
    predictions: list[float] = []
    for index in range(horizon):
        seasonal = window[index % len(window)]
        trend = window.mean()
        next_value = 0.65 * seasonal + 0.35 * trend
        predictions.append(float(next_value))
    return np.asarray(predictions, dtype=float)


def forecast_horizons(
    metadata_path: str | Path | None = None,
    model_path: str | Path | None = None,
    horizon: int = 168,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    metadata_path = Path(metadata_path) if metadata_path else paths.demand_metadata
    model_path = Path(model_path) if model_path else paths.lstm_model
    metadata = load_json(metadata_path, default={}) or {}

    if not metadata:
        return {"next_hour": 0.0, "next_day": 0.0, "next_week": 0.0, "series": []}

    if metadata.get("model_type") == "lstm" and tf is not None and model_path.exists():
        try:
            model = tf.keras.models.load_model(model_path, compile=False)
            window = np.asarray(metadata["last_window"], dtype=float).reshape(1, metadata["lookback"], 1)
            predictions_scaled: list[float] = []
            for _ in range(horizon):
                next_value = float(model.predict(window, verbose=0)[0][0])
                predictions_scaled.append(next_value)
                window = np.concatenate([window[:, 1:, :], np.array(next_value).reshape(1, 1, 1)], axis=1)
            predictions = _inverse_scale(np.asarray(predictions_scaled), metadata)
        except Exception:
            predictions = _baseline_forecast(metadata.get("history_values", []), horizon=horizon)
    else:
        predictions = _baseline_forecast(metadata.get("history_values", []), horizon=horizon)

    chart_series = [
        {"step": index + 1, "forecast_kwh": round(float(value), 2)}
        for index, value in enumerate(predictions[:48])
    ]
    return {
        "next_hour": round(float(predictions[0]), 2) if len(predictions) else 0.0,
        "next_day": round(float(predictions[:24].sum()), 2) if len(predictions) >= 24 else round(float(predictions.sum()), 2),
        "next_week": round(float(predictions[:168].sum()), 2) if len(predictions) >= 168 else round(float(predictions.sum()), 2),
        "series": chart_series,
        "model_type": metadata.get("model_type", "baseline"),
    }
