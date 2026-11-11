from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src.detect_anomaly import score_anomalies
from src.feature_engineering import build_feature_matrix
from utils.helpers import ensure_project_dirs, load_joblib, load_json


def _predict_probability(model: object, features: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]
    if hasattr(model, "decision_function"):
        decision = model.decision_function(features)
        return 1.0 / (1.0 + np.exp(-decision))
    return np.asarray(model.predict(features), dtype=float)


def _calibrate_theft_probability(anomaly_frame: pd.DataFrame, rf_probability: np.ndarray, boost_probability: np.ndarray) -> np.ndarray:
    """Blend classifier outputs only; generator and target context is not predictive evidence."""
    del anomaly_frame
    return np.clip(0.45 * rf_probability + 0.55 * boost_probability, 0.0, 1.0)


def classify_meter_events(
    dataframe: pd.DataFrame,
    metadata_path: str | Path | None = None,
    random_forest_path: str | Path | None = None,
    boost_model_path: str | Path | None = None,
) -> pd.DataFrame:
    paths = ensure_project_dirs()
    metadata_path = Path(metadata_path) if metadata_path else paths.model_metadata
    random_forest_path = Path(random_forest_path) if random_forest_path else paths.random_forest
    boost_model_path = Path(boost_model_path) if boost_model_path else paths.xgboost_model

    metadata = load_json(metadata_path, default={}) or {}
    anomaly_frame = score_anomalies(dataframe, metadata_path=metadata_path)
    _, features = build_feature_matrix(anomaly_frame, model_columns=metadata.get("feature_columns"))

    rf_model = load_joblib(random_forest_path)
    boost_model = load_joblib(boost_model_path)

    rf_probability = _predict_probability(rf_model, features)
    boost_probability = _predict_probability(boost_model, features)
    theft_probability = _calibrate_theft_probability(anomaly_frame, rf_probability, boost_probability)

    result = anomaly_frame.copy()
    result["random_forest_probability"] = rf_probability
    result["xgboost_probability"] = boost_probability
    result["theft_probability"] = theft_probability
    theft_threshold = float(metadata.get("theft_threshold", 0.5))
    result["status"] = np.select(
        [
            result["theft_probability"] >= theft_threshold,
            result["is_anomaly"] == 1,
            result["wastage_score"] >= 0.35,
        ],
        [
            "Electricity Theft",
            "Anomaly",
            "Power Wastage",
        ],
        default="Normal",
    )
    # Keep outcomes and generator diagnostics out of the prediction surface.
    return result.drop(columns=["is_theft", "theft_type", "seeded_theft_probability"], errors="ignore")
