from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def sample_meter_frame() -> pd.DataFrame:
    timestamps = pd.date_range("2026-03-12 00:00:00", periods=6, freq="h")
    rows = []
    for meter_id, area, latitude, longitude, profile in [
        ("M0001", "Whitefield", 12.9698, 77.7499, "residential"),
        ("M0002", "Electronic City", 12.8452, 77.6602, "commercial"),
    ]:
        for index, timestamp in enumerate(timestamps):
            rows.append(
                {
                    "meter_id": meter_id,
                    "timestamp": timestamp,
                    "region": "Bengaluru",
                    "area": area,
                    "latitude": latitude,
                    "longitude": longitude,
                    "voltage": 228.0 + index,
                    "current": 5.0 + index * 0.1,
                    "power": 1.4 + index * 0.05,
                    "consumption_kwh": 1.1 + index * 0.04,
                    "power_factor": 0.92,
                    "temperature": 27.0 + index * 0.2,
                    "humidity": 68.0,
                    "rainfall": 0.0,
                    "wind_speed": 2.1,
                    "weather_condition": "Clear",
                    "is_theft": 0,
                    "expected_consumption_kwh": 1.0 + index * 0.04,
                    "wastage_score": 0.08,
                    "usage_profile": profile,
                    "theft_type": "none",
                    "seeded_theft_probability": 0.0,
                }
            )
    return pd.DataFrame(rows)

