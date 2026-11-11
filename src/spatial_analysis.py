from __future__ import annotations

from pathlib import Path
import shutil

import pandas as pd

from utils.helpers import ensure_project_dirs

try:  # pragma: no cover - optional at runtime
    import folium
    from folium.plugins import HeatMap
except Exception:  # pragma: no cover - optional at runtime
    folium = None
    HeatMap = None


def build_theft_heatmap(dataframe: pd.DataFrame, output_path: str | Path | None = None) -> Path:
    paths = ensure_project_dirs()
    output_path = Path(output_path) if output_path else paths.map_path
    dashboard_output = paths.dashboard_dir / "theft_heatmap.html"
    if output_path.exists() and output_path.is_dir():
        output_path = output_path / "theft_heatmap.html"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dashboard_output.parent.mkdir(parents=True, exist_ok=True)

    theft_frame = dataframe.copy()
    if "timestamp" in theft_frame.columns and not theft_frame.empty:
        theft_frame["timestamp"] = pd.to_datetime(theft_frame["timestamp"], errors="coerce")
        latest_timestamp = theft_frame["timestamp"].max()
        if pd.notna(latest_timestamp):
            theft_frame = theft_frame.loc[theft_frame["timestamp"] == latest_timestamp].copy()
    if "status" in theft_frame:
        theft_frame = theft_frame.loc[theft_frame["status"] == "Electricity Theft"]
    elif "theft_probability" in theft_frame:
        theft_frame = theft_frame.loc[theft_frame["theft_probability"] >= 0.75]
    elif "is_theft" in theft_frame:
        theft_frame = theft_frame.loc[theft_frame["is_theft"] == 1]

    if folium is None or HeatMap is None:
        html = "<html><body><h2>Folium is not installed.</h2><p>Install dependencies and rerun the pipeline to generate the theft heatmap.</p></body></html>"
        output_path.write_text(
            html,
            encoding="utf-8",
        )
        dashboard_output.write_text(html, encoding="utf-8")
        return output_path

    # Use the same public OpenStreetMap tile source as the interactive dashboard.
    # This keeps the standalone Folium view usable without a provider API key.
    map_object = folium.Map(location=[12.9716, 77.5946], zoom_start=11, tiles="OpenStreetMap")
    if theft_frame.empty:
        folium.Marker([12.9716, 77.5946], popup="No theft alerts available.").add_to(map_object)
        map_object.save(output_path)
        shutil.copyfile(output_path, dashboard_output)
        return output_path

    heat_data = theft_frame[["latitude", "longitude", "theft_probability"]].fillna(0.0).values.tolist()
    HeatMap(heat_data, radius=18, blur=14, max_zoom=13).add_to(map_object)

    preview = theft_frame.sort_values("theft_probability", ascending=False).head(150)
    for _, row in preview.iterrows():
        folium.CircleMarker(
            location=[row["latitude"], row["longitude"]],
            radius=5,
            color="#c2410c",
            fill=True,
            fill_opacity=0.8,
            popup=f"{row['meter_id']} | {row['area']} | {row.get('status', 'Theft')}",
        ).add_to(map_object)

    map_object.save(output_path)
    shutil.copyfile(output_path, dashboard_output)
    return output_path
