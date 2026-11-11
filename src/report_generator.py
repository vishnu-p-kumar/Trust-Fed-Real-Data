from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.backends.backend_pdf import PdfPages

from src.preprocess import aggregate_region_consumption, aggregate_weather_impact, build_overview_snapshot
from utils.helpers import ensure_project_dirs


def generate_daily_report(
    predictions: pd.DataFrame,
    forecast: dict[str, Any] | None = None,
    output_path: str | Path | None = None,
) -> Path:
    paths = ensure_project_dirs()
    output_path = Path(output_path) if output_path else paths.daily_report
    output_path.parent.mkdir(parents=True, exist_ok=True)

    latest = predictions.sort_values("timestamp").groupby("meter_id", as_index=False).tail(1) if not predictions.empty else predictions
    overview = build_overview_snapshot(latest)
    region = aggregate_region_consumption(latest).head(8)
    weather = aggregate_weather_impact(predictions.tail(4000))
    theft = latest.loc[latest.get("status", pd.Series(dtype=object)) == "Electricity Theft"].head(10)
    forecast = forecast or {"next_hour": 0.0, "next_day": 0.0, "next_week": 0.0}

    with PdfPages(output_path) as pdf:
        fig, axes = plt.subplots(2, 2, figsize=(13, 9))
        fig.suptitle("Smart Grid Daily Energy Report", fontsize=18, fontweight="bold")

        axes[0, 0].axis("off")
        summary_lines = [
            f"Generated: {pd.Timestamp.utcnow().tz_localize(None).isoformat()}",
            f"Active meters: {overview['active_meters']}",
            f"Anomalies: {overview['anomalies']}",
            f"Theft alerts: {overview['theft']}",
            f"Power wastage alerts: {overview['wastage']}",
            f"Forecast next hour: {forecast.get('next_hour', 0.0)} kWh",
            f"Forecast next day: {forecast.get('next_day', 0.0)} kWh",
            f"Forecast next week: {forecast.get('next_week', 0.0)} kWh",
        ]
        axes[0, 0].text(0.02, 0.98, "\n".join(summary_lines), va="top", ha="left", fontsize=11)

        if not region.empty:
            axes[0, 1].bar(region["area"], region["consumption_kwh"], color="#0f766e")
            axes[0, 1].set_title("Region Consumption")
            axes[0, 1].tick_params(axis="x", rotation=45)
        else:
            axes[0, 1].axis("off")

        if not weather.empty:
            axes[1, 0].plot(weather["temperature_band"].astype(str), weather["avg_consumption"], marker="o", color="#c9772b")
            axes[1, 0].set_title("Weather Impact")
        else:
            axes[1, 0].axis("off")

        if not theft.empty:
            axes[1, 1].axis("off")
            theft_lines = [
                f"{row.meter_id} | {row.area} | Prob {float(getattr(row, 'theft_probability', 0.0)):.2f} | Risk {float(getattr(row, 'risk_score', 0.0)):.1f}"
                for row in theft.itertuples()
            ]
            axes[1, 1].text(0.02, 0.98, "Top Theft Incidents\n\n" + "\n".join(theft_lines), va="top", ha="left", fontsize=10)
        else:
            axes[1, 1].axis("off")
            axes[1, 1].text(0.02, 0.98, "No theft incidents detected in the latest snapshot.", va="top", ha="left", fontsize=11)

        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

    return output_path
