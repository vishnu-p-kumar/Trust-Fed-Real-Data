from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from src.demand_forecasting import build_demand_series
from utils.helpers import ensure_project_dirs, load_json, save_json

try:  # pragma: no cover - optional at runtime
    import torch
    from torch import nn
except Exception:  # pragma: no cover - optional at runtime
    torch = None
    nn = None


def _create_sequences(values: np.ndarray, lookback: int) -> tuple[np.ndarray, np.ndarray]:
    features, targets = [], []
    for index in range(lookback, len(values)):
        features.append(values[index - lookback : index])
        targets.append(values[index])
    return np.asarray(features), np.asarray(targets)


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
        predictions.append(float(0.6 * window[index % len(window)] + 0.4 * window.mean()))
    return np.asarray(predictions, dtype=float)


if torch is not None:  # pragma: no branch
    class TransformerRegressor(nn.Module):
        def __init__(self, lookback: int, d_model: int = 32, nhead: int = 4, num_layers: int = 2) -> None:
            super().__init__()
            self.lookback = lookback
            self.input_projection = nn.Linear(1, d_model)
            self.positional = nn.Parameter(torch.zeros(1, lookback, d_model))
            encoder_layer = nn.TransformerEncoderLayer(
                d_model=d_model,
                nhead=nhead,
                dim_feedforward=64,
                dropout=0.1,
                batch_first=True,
            )
            self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.head = nn.Sequential(nn.Linear(d_model, 32), nn.ReLU(), nn.Linear(32, 1))

        def forward(self, x: Any) -> Any:
            encoded = self.input_projection(x) + self.positional[:, : x.shape[1], :]
            sequence = self.encoder(encoded)
            return self.head(sequence[:, -1, :])


def train_transformer_forecaster(
    dataframe: pd.DataFrame,
    lookback: int = 24,
    epochs: int = 4,
    batch_size: int = 64,
    model_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    model_path = Path(model_path) if model_path else paths.transformer_model
    metadata_path = Path(metadata_path) if metadata_path else paths.transformer_metadata

    series = build_demand_series(dataframe)
    if series.empty or len(series) <= lookback + 8:
        metadata = {"model_type": "baseline", "lookback": lookback, "history_values": [], "timestamps": []}
        save_json(metadata, metadata_path)
        return metadata

    values = series["consumption_kwh"].astype(float).to_numpy()
    scaler = MinMaxScaler()
    scaled = scaler.fit_transform(values.reshape(-1, 1)).flatten()
    features, targets = _create_sequences(scaled, lookback=lookback)

    metadata: dict[str, Any] = {
        "lookback": lookback,
        "timestamps": [timestamp.isoformat() for timestamp in series["timestamp"].tail(168)],
        "history_values": values[-168:].round(3).tolist(),
        "scaler_min": float(scaler.data_min_[0]),
        "scaler_max": float(scaler.data_max_[0]),
        "last_window": scaled[-lookback:].round(6).tolist(),
    }

    if torch is None or len(features) < 96:
        metadata["model_type"] = "baseline"
        save_json(metadata, metadata_path)
        return metadata

    device = torch.device("cpu")
    x_tensor = torch.tensor(features.reshape((-1, lookback, 1)), dtype=torch.float32, device=device)
    y_tensor = torch.tensor(targets.reshape((-1, 1)), dtype=torch.float32, device=device)

    model = TransformerRegressor(lookback=lookback).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    loss_fn = nn.MSELoss()

    model.train()
    for _ in range(epochs):
        permutation = torch.randperm(x_tensor.size(0))
        for start in range(0, x_tensor.size(0), batch_size):
            batch_index = permutation[start : start + batch_size]
            batch_x = x_tensor[batch_index]
            batch_y = y_tensor[batch_index]
            optimizer.zero_grad()
            loss = loss_fn(model(batch_x), batch_y)
            loss.backward()
            optimizer.step()

    torch.save({"state_dict": model.state_dict(), "lookback": lookback}, model_path)
    metadata["model_type"] = "transformer"
    save_json(metadata, metadata_path)
    return metadata


def forecast_transformer_horizons(
    metadata_path: str | Path | None = None,
    model_path: str | Path | None = None,
    horizon: int = 168,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    metadata_path = Path(metadata_path) if metadata_path else paths.transformer_metadata
    model_path = Path(model_path) if model_path else paths.transformer_model
    metadata = load_json(metadata_path, default={}) or {}

    if not metadata:
        return {"next_hour": 0.0, "next_day": 0.0, "next_week": 0.0, "series": [], "model_type": "baseline"}

    if metadata.get("model_type") == "transformer" and torch is not None and model_path.exists():
        try:
            checkpoint = torch.load(model_path, map_location="cpu")
            model = TransformerRegressor(lookback=int(checkpoint.get("lookback", metadata["lookback"])))
            model.load_state_dict(checkpoint["state_dict"])
            model.eval()
            window = np.asarray(metadata["last_window"], dtype=float).reshape(1, metadata["lookback"], 1)
            predictions_scaled: list[float] = []
            for _ in range(horizon):
                batch = torch.tensor(window, dtype=torch.float32)
                with torch.no_grad():
                    next_value = float(model(batch).cpu().numpy().ravel()[0])
                next_value = float(np.clip(next_value, 0.0, 1.5))
                predictions_scaled.append(next_value)
                window = np.concatenate([window[:, 1:, :], np.array(next_value).reshape(1, 1, 1)], axis=1)
            predictions = _inverse_scale(np.asarray(predictions_scaled), metadata)
        except Exception:
            predictions = _baseline_forecast(metadata.get("history_values", []), horizon=horizon)
    else:
        predictions = _baseline_forecast(metadata.get("history_values", []), horizon=horizon)

    return {
        "next_hour": round(float(predictions[0]), 2) if len(predictions) else 0.0,
        "next_day": round(float(predictions[:24].sum()), 2) if len(predictions) >= 24 else round(float(predictions.sum()), 2),
        "next_week": round(float(predictions[:168].sum()), 2) if len(predictions) >= 168 else round(float(predictions.sum()), 2),
        "series": [{"step": index + 1, "forecast_kwh": round(float(value), 2)} for index, value in enumerate(predictions[:48])],
        "model_type": metadata.get("model_type", "baseline"),
    }
