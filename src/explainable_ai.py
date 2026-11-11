from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.feature_engineering import build_feature_matrix
from utils.helpers import ensure_project_dirs, load_joblib, load_json

try:  # pragma: no cover - optional at runtime
    import shap
except Exception:  # pragma: no cover - optional at runtime
    shap = None


FRIENDLY_FEATURES = {
    "consumption_kwh": "Sudden consumption shift",
    "night_usage_ratio": "High night-time usage",
    "voltage_irregularity": "Voltage irregularity",
    "current_power_gap": "Power-current mismatch",
    "power_factor_loss": "Power factor loss",
    "wastage_score": "Abnormal energy wastage",
    "rolling_average_consumption": "Deviation from normal rolling demand",
    "temperature": "Weather-driven load change",
    "humidity": "Humidity-linked load pattern",
    "rainfall": "Rainfall effect on electricity usage",
}

HEURISTIC_REASON_COLUMNS = [
    "theft_probability",
    "anomaly_score",
    "wastage_score",
    "night_usage_ratio",
    "voltage_irregularity",
    "current_power_gap",
    "power_factor_loss",
    "consumption_kwh",
]


def _normalise_feature_name(name: str) -> str:
    for key, label in FRIENDLY_FEATURES.items():
        if name.startswith(key):
            return label
    return name.replace("_", " ").title()


def _feature_contributions(model: Any, feature_row: pd.DataFrame) -> pd.Series:
    if shap is not None:
        try:
            explainer = shap.TreeExplainer(model)
            shap_values = explainer.shap_values(feature_row)
            if isinstance(shap_values, list):
                values = np.asarray(shap_values[-1])[0]
            elif hasattr(shap_values, "values"):
                raw = np.asarray(shap_values.values)
                values = raw[0, :, -1] if raw.ndim == 3 else raw[0]
            else:
                values = np.asarray(shap_values)[0]
            return pd.Series(values, index=feature_row.columns)
        except Exception:
            pass

    importances = getattr(model, "feature_importances_", np.ones(feature_row.shape[1]))
    values = feature_row.iloc[0].to_numpy(dtype=float) * np.asarray(importances, dtype=float)
    return pd.Series(values, index=feature_row.columns)


def _fallback_explanation(dataframe: pd.DataFrame, top_k: int) -> dict[str, Any]:
    enriched, _ = build_feature_matrix(dataframe)
    if enriched.empty:
        return {"reason": [], "summary": "No features available for explanation."}

    row = enriched.iloc[0]
    scores: dict[str, float] = {}
    for column in HEURISTIC_REASON_COLUMNS:
        if column in row.index:
            scores[column] = abs(float(pd.to_numeric(pd.Series([row.get(column)]), errors="coerce").fillna(0.0).iloc[0]))

    if not scores:
        scores = {"consumption_kwh": 0.0}
    reasons = [
        _normalise_feature_name(name)
        for name, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    ]
    return {
        "meter_id": row.get("meter_id"),
        "area": row.get("area"),
        "reason": reasons,
        "summary": ", ".join(reasons),
    }


def explain_prediction(
    dataframe: pd.DataFrame,
    top_k: int = 3,
    model_path: str | Path | None = None,
    metadata_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    model_path = Path(model_path) if model_path else paths.xgboost_model
    metadata_path = Path(metadata_path) if metadata_path else paths.model_metadata
    metadata = load_json(metadata_path, default={}) or {}
    if not model_path.exists():
        return _fallback_explanation(dataframe, top_k=top_k)
    try:
        model = load_joblib(model_path)
    except Exception:
        return _fallback_explanation(dataframe, top_k=top_k)

    enriched, features = build_feature_matrix(dataframe, model_columns=metadata.get("feature_columns"))
    if features.empty:
        return {"reason": [], "summary": "No features available for explanation."}

    feature_row = features.head(1)
    contributions = _feature_contributions(model, feature_row).abs().sort_values(ascending=False).head(top_k)
    reasons = [_normalise_feature_name(name) for name in contributions.index]

    row = enriched.iloc[0]
    return {
        "meter_id": row.get("meter_id"),
        "area": row.get("area"),
        "reason": reasons,
        "summary": ", ".join(reasons),
    }


def explain_alerts(dataframe: pd.DataFrame, limit: int = 5) -> list[dict[str, Any]]:
    sort_columns = [column for column in ["theft_probability", "anomaly_score"] if column in dataframe.columns]
    alerts = dataframe.sort_values(sort_columns, ascending=False).head(limit) if sort_columns else dataframe.head(limit)
    explanations: list[dict[str, Any]] = []
    for _, row in alerts.iterrows():
        explanations.append(explain_prediction(pd.DataFrame([row])))
    return explanations
