from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.feature_engineering import build_feature_matrix
from utils.helpers import ensure_project_dirs, load_joblib, load_json


def score_anomalies(
    dataframe: pd.DataFrame,
    model_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> pd.DataFrame:
    paths = ensure_project_dirs()
    model_path = Path(model_path) if model_path else paths.isolation_forest
    metadata_path = Path(metadata_path) if metadata_path else paths.model_metadata

    metadata = load_json(metadata_path, default={}) or {}
    model = load_joblib(model_path)
    enriched, features = build_feature_matrix(dataframe, model_columns=metadata.get("feature_columns"))
    if features.empty:
        enriched["anomaly_score"] = pd.Series(dtype=float)
        enriched["is_anomaly"] = pd.Series(dtype=int)
        return enriched

    anomaly_score = -model.score_samples(features)
    threshold = float(metadata.get("anomaly_threshold", anomaly_score.mean() if len(anomaly_score) else 0.0))
    enriched["anomaly_score"] = anomaly_score
    enriched["is_anomaly"] = (anomaly_score >= threshold).astype(int)
    return enriched
