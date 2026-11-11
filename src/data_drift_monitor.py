from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from utils.helpers import ensure_project_dirs, save_json

try:  # pragma: no cover - optional at runtime
    from evidently import Report
    from evidently.presets import DataDriftPreset, DataSummaryPreset
except Exception:  # pragma: no cover - optional at runtime
    Report = None
    DataDriftPreset = None
    DataSummaryPreset = None


def _numeric_subset(reference_frame: pd.DataFrame, current_frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    common = [column for column in reference_frame.columns if column in current_frame.columns]
    numeric_columns = [
        column
        for column in common
        if pd.api.types.is_numeric_dtype(reference_frame[column]) and pd.api.types.is_numeric_dtype(current_frame[column])
    ]
    if not numeric_columns:
        return pd.DataFrame(), pd.DataFrame()
    return reference_frame[numeric_columns].copy(), current_frame[numeric_columns].copy()


def _coerce_evidently_report(report: Any) -> dict[str, Any]:
    for method_name in ["as_dict", "dict"]:
        method = getattr(report, method_name, None)
        if callable(method):
            try:
                payload = method()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                pass
    method = getattr(report, "json", None)
    if callable(method):
        try:
            import json

            return json.loads(method())
        except Exception:
            pass
    return {}


def _fallback_feature_drift(reference_frame: pd.DataFrame, current_frame: pd.DataFrame) -> list[dict[str, Any]]:
    drift_rows: list[dict[str, Any]] = []
    for column in reference_frame.columns:
        reference = pd.to_numeric(reference_frame[column], errors="coerce").dropna()
        current = pd.to_numeric(current_frame[column], errors="coerce").dropna()
        reference_mean = float(reference.mean()) if not reference.empty else 0.0
        current_mean = float(current.mean()) if not current.empty else 0.0
        baseline = max(abs(reference_mean), 1e-6)
        relative_shift = abs(current_mean - reference_mean) / baseline
        drift_rows.append(
            {
                "feature": column,
                "reference_mean": round(reference_mean, 4),
                "current_mean": round(current_mean, 4),
                "relative_shift": round(float(relative_shift), 4),
                "drift_detected": relative_shift >= 0.12,
            }
        )
    drift_rows.sort(key=lambda item: item["relative_shift"], reverse=True)
    return drift_rows


def _numeric_series(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column in dataframe.columns:
        return pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)
    return pd.Series(0.0, index=dataframe.index, dtype=float)


def generate_drift_report(
    reference_frame: pd.DataFrame,
    current_frame: pd.DataFrame,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    output_path = Path(output_path) if output_path else paths.drift_report

    reference_numeric, current_numeric = _numeric_subset(reference_frame, current_frame)
    if reference_numeric.empty or current_numeric.empty:
        report = {
            "generated_at": pd.Timestamp.utcnow().tz_localize(None).isoformat(),
            "method": "fallback",
            "drift_detected": False,
            "feature_drift": [],
            "concept_drift": {"theft_rate_shift": 0.0, "prediction_rate_shift": 0.0, "detected": False},
            "data_quality": {"reference_missing_pct": 0.0, "current_missing_pct": 0.0, "issues": []},
        }
        save_json(report, output_path)
        return report

    feature_drift = _fallback_feature_drift(reference_numeric, current_numeric)
    report_method = "fallback"
    evidently_summary: dict[str, Any] = {}
    if Report is not None and DataDriftPreset is not None and DataSummaryPreset is not None:
        try:
            evidently_report = Report([DataDriftPreset(), DataSummaryPreset()])
            evidently_snapshot = evidently_report.run(reference_data=reference_numeric, current_data=current_numeric)
            evidently_summary = _coerce_evidently_report(evidently_snapshot)
            report_method = "evidently"
        except Exception:
            evidently_summary = {}

    reference_theft = float(_numeric_series(reference_frame, "is_theft").mean())
    current_theft = float(_numeric_series(current_frame, "is_theft").mean())
    reference_pred = float(_numeric_series(reference_frame, "theft_probability").mean())
    current_pred = float(_numeric_series(current_frame, "theft_probability").mean())
    concept_shift = {
        "theft_rate_shift": round(current_theft - reference_theft, 4),
        "prediction_rate_shift": round(current_pred - reference_pred, 4),
        "detected": abs(current_theft - reference_theft) >= 0.05 or abs(current_pred - reference_pred) >= 0.08,
    }

    reference_missing = float(reference_frame.isna().mean().mean()) if not reference_frame.empty else 0.0
    current_missing = float(current_frame.isna().mean().mean()) if not current_frame.empty else 0.0
    issues: list[str] = []
    if current_missing >= 0.03:
        issues.append("Incoming data has elevated missing-value ratio.")
    if current_frame.duplicated(subset=["meter_id", "timestamp"]).any():
        issues.append("Duplicate meter/timestamp rows detected in current data.")

    report = {
        "generated_at": pd.Timestamp.utcnow().tz_localize(None).isoformat(),
        "method": report_method,
        "drift_detected": any(item["drift_detected"] for item in feature_drift) or concept_shift["detected"] or bool(issues),
        "feature_drift": feature_drift[:12],
        "concept_drift": concept_shift,
        "data_quality": {
            "reference_missing_pct": round(reference_missing * 100.0, 3),
            "current_missing_pct": round(current_missing * 100.0, 3),
            "issues": issues,
        },
        "evidently_summary": evidently_summary,
    }
    save_json(report, output_path)
    return report
