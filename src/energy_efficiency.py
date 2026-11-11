from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def calculate_efficiency_metrics(dataframe: pd.DataFrame) -> pd.DataFrame:
    frame = dataframe.copy()
    if frame.empty:
        frame["efficiency_score"] = pd.Series(dtype=float)
        frame["wastage_flag"] = pd.Series(dtype=int)
        frame["estimated_losses_kwh"] = pd.Series(dtype=float)
        return frame

    expected = pd.to_numeric(frame.get("expected_consumption_kwh", frame.get("consumption_kwh", 0.0)), errors="coerce").fillna(0.0)
    consumed = pd.to_numeric(frame.get("consumption_kwh", 0.0), errors="coerce").fillna(0.0).clip(lower=0.0)
    power_factor = pd.to_numeric(frame.get("power_factor", 1.0), errors="coerce").fillna(1.0).clip(lower=0.0, upper=1.0)
    useful_energy = np.minimum(expected, consumed)
    total_energy = np.maximum(consumed, expected).replace(0.0, np.nan)
    frame["efficiency_score"] = ((useful_energy / total_energy) * power_factor).replace([np.inf, -np.inf], np.nan).fillna(0.0)
    frame["efficiency_score"] = (frame["efficiency_score"].clip(0.0, 1.0) * 100.0).round(2)
    frame["estimated_losses_kwh"] = (np.maximum(consumed - useful_energy, 0.0) + (1.0 - power_factor) * consumed).round(3)
    wastage_score = pd.to_numeric(frame.get("wastage_score", 0.0), errors="coerce").fillna(0.0)
    frame["wastage_flag"] = ((frame["efficiency_score"] < 72.0) | (wastage_score >= 0.25)).astype(int)
    return frame


def summarise_efficiency(dataframe: pd.DataFrame, limit: int = 20) -> dict[str, Any]:
    frame = dataframe if "efficiency_score" in dataframe.columns else calculate_efficiency_metrics(dataframe)
    ranked = frame.sort_values(["wastage_flag", "efficiency_score"], ascending=[False, True]).head(limit)
    summary = {
        "low_efficiency": int((frame.get("wastage_flag", pd.Series(dtype=int)) == 1).sum()),
        "average_efficiency": round(float(frame.get("efficiency_score", pd.Series(dtype=float)).mean()), 2) if not frame.empty else 0.0,
        "estimated_losses_kwh": round(float(frame.get("estimated_losses_kwh", pd.Series(dtype=float)).sum()), 2) if not frame.empty else 0.0,
    }
    return {
        "summary": summary,
        "records": ranked.replace({np.nan: None}).to_dict(orient="records"),
    }
