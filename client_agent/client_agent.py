#!/usr/bin/env python3
"""Train locally with the shared feature transform and submit model parameters only."""
from __future__ import annotations
import argparse, hashlib, hmac, json, os
import numpy as np
import pandas as pd
import requests

FEATURE_TRANSFORMS = {
    "voltage": (230.0, 20.0), "current": (0.0, 10.0), "power": (0.0, 2.0),
    "consumption_kwh": (0.0, 0.5), "power_factor": (0.9, 0.2),
}

def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))

def train_local(X, y, initial_weights, initial_bias, features, epochs, learning_rate):
    transforms = np.asarray([FEATURE_TRANSFORMS[name] for name in features], dtype=float)
    centers, scales = transforms[:, 0], transforms[:, 1]
    raw_weights = np.asarray(initial_weights, dtype=float) if len(initial_weights) else np.zeros(X.shape[1])
    weights = raw_weights * scales
    bias = float(initial_bias) + float(np.dot(raw_weights, centers))
    normalized = (X - centers) / scales
    positive, negative = int(np.sum(y == 1)), int(np.sum(y == 0))
    class_weights = np.where(y == 1, len(y) / (2 * positive), len(y) / (2 * negative))
    for _ in range(epochs):
        probabilities = sigmoid(normalized @ weights + bias)
        error = (probabilities - y) * class_weights
        gradient = normalized.T @ error / len(y) + 1e-4 * weights
        bias_gradient = float(error.mean())
        weights -= learning_rate * np.clip(gradient, -10, 10)
        bias -= learning_rate * float(np.clip(bias_gradient, -10, 10))
        norm = float(np.linalg.norm(weights))
        if norm > 20:
            weights *= 20 / norm
    raw_weights = weights / scales
    raw_bias = bias - float(np.dot(raw_weights, centers))
    return raw_weights, raw_bias

def main():
    parser = argparse.ArgumentParser(description="TrustFedGrid independent client agent")
    parser.add_argument("--api", default="http://127.0.0.1:8000")
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--client-secret", required=True)
    parser.add_argument("--csv", required=True, help="Local CSV path; file is not uploaded")
    parser.add_argument("--label", default="is_theft")
    parser.add_argument("--features", required=True, help="Shared numeric columns: voltage,current,power,consumption_kwh,power_factor")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--learning-rate", type=float, default=0.03)
    args = parser.parse_args()
    features = [name.strip() for name in args.features.split(",") if name.strip()]
    unsupported = [name for name in features if name not in FEATURE_TRANSFORMS]
    if unsupported:
        parser.error("Unsupported shared feature(s): " + ", ".join(unsupported))
    if not features or len(set(features)) != len(features):
        parser.error("Features must be non-empty and contain no duplicates.")
    frame = pd.read_csv(args.csv)
    missing = [name for name in features + [args.label] if name not in frame.columns]
    if missing:
        parser.error("CSV missing columns: " + ", ".join(missing))
    numeric = frame[features + [args.label]].apply(pd.to_numeric, errors="coerce")
    if numeric.isna().any().any() or not np.isfinite(numeric.to_numpy(dtype=float)).all():
        parser.error("CSV contains missing or non-numeric feature or label values; fix the rows before submitting.")
    X = numeric[features].to_numpy(dtype=float)
    y = numeric[args.label].to_numpy(dtype=float)
    if not set(np.unique(y)).issubset({0.0, 1.0}) or len(np.unique(y)) < 2:
        parser.error("Need both binary label classes (0 and 1).")
    poisoned_row_count = 0
    if "is_poisoned" in frame.columns:
        marker = pd.to_numeric(frame["is_poisoned"], errors="coerce")
        if marker.isna().any() or not set(marker.unique()).issubset({0, 1}):
            parser.error("is_poisoned must contain only 0 or 1 when present.")
        poisoned_row_count = int((marker == 1).sum())

    session = requests.Session()
    login = session.post(args.api.rstrip("/") + "/client/auth/login",
        json={"identifier": args.client_id, "password": args.password}, timeout=30)
    login.raise_for_status()
    state = session.get(args.api.rstrip("/") + "/api/client/me", timeout=30)
    state.raise_for_status()
    global_model = state.json()["global_model"]
    if global_model["weights"] and len(global_model["weights"]) != X.shape[1]:
        parser.error(f"Global model expects {len(global_model['weights'])} features; supplied {X.shape[1]}.")
    weights, bias = train_local(X, y, global_model["weights"], global_model["bias"], features, args.epochs, args.learning_rate)
    with open(args.csv, "rb") as csv_file:
        digest = hashlib.sha256(csv_file.read()).hexdigest()
    dataset_meta = {"filename": os.path.basename(args.csv), "sha256": digest, "row_count": int(len(y)),
                    "feature_columns": features, "label_column": args.label}
    meta = session.post(args.api.rstrip("/") + "/api/client/datasets", json=dataset_meta, timeout=30)
    meta.raise_for_status()
    update_payload = {"round_id": args.round_id, "weights": weights.tolist(), "bias": float(bias),
                      "sample_count": int(len(y)), "feature_columns": features,
                      "poisoned_row_count": poisoned_row_count}
    signed_payload = {"client_id": state.json()["client"]["client_id"], "round_id": args.round_id,
                      "weights": weights.tolist(), "bias": float(bias), "sample_count": int(len(y))}
    canonical = json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))
    signing_key = hashlib.sha256(args.client_secret.encode()).digest()
    signature = hmac.new(signing_key, canonical.encode(), hashlib.sha256).hexdigest()
    response = session.post(args.api.rstrip("/") + "/api/client/federated/update",
        headers={"X-Client-Signature": signature}, json=update_payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    print(json.dumps({key: value for key, value in result.items() if key not in {"weights", "bias"}}, indent=2))
    print("Raw CSV rows were processed locally and were not uploaded.")

if __name__ == "__main__":
    main()
