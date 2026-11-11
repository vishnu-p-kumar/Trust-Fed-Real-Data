from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import requests

from utils.helpers import AREA_COORDINATES


@dataclass
class WeatherSnapshot:
    temperature: float
    humidity: float
    rainfall: float
    wind_speed: float
    weather_condition: str
    source: str


class WeatherService:
    """Uses OpenWeather when configured and falls back to a Bengaluru climate simulator."""

    def __init__(self, api_key: str | None = None, timeout: int = 10) -> None:
        self.api_key = api_key or os.getenv("OPENWEATHER_API_KEY")
        self.timeout = timeout
        self.session = requests.Session()

    def fetch_live_weather(self, latitude: float, longitude: float) -> WeatherSnapshot:
        if not self.api_key:
            raise RuntimeError("OPENWEATHER_API_KEY is not configured.")
        response = self.session.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={
                "lat": latitude,
                "lon": longitude,
                "appid": self.api_key,
                "units": "metric",
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        rainfall = float(payload.get("rain", {}).get("1h", 0.0))
        return WeatherSnapshot(
            temperature=float(payload["main"]["temp"]),
            humidity=float(payload["main"]["humidity"]),
            rainfall=rainfall,
            wind_speed=float(payload.get("wind", {}).get("speed", 0.0)),
            weather_condition=str(payload["weather"][0]["main"]),
            source="openweather",
        )

    def synthetic_hourly_weather(self, timestamps: pd.DatetimeIndex, area: str) -> pd.DataFrame:
        if area not in AREA_COORDINATES:
            raise KeyError(f"Unknown Bengaluru area: {area}")

        hour = timestamps.hour.to_numpy()
        dayofyear = timestamps.dayofyear.to_numpy()
        month = timestamps.month.to_numpy()

        base_temp = 23 + 5 * np.sin((dayofyear / 365.0) * 2 * np.pi) + 4 * np.sin(((hour - 13) / 24.0) * 2 * np.pi)
        humidity = 68 + 16 * np.sin((dayofyear / 365.0) * 2 * np.pi + 0.9) - 8 * np.sin((hour / 24.0) * 2 * np.pi)
        monsoon = np.where(np.isin(month, [6, 7, 8, 9]), 1.0, 0.0)
        rainfall = np.maximum(0.0, np.random.gamma(shape=1.8, scale=0.7, size=len(timestamps)) * monsoon)
        wind_speed = np.maximum(0.5, 1.8 + 1.2 * np.sin((hour / 24.0) * 2 * np.pi + 0.4) + np.random.normal(0, 0.35, len(timestamps)))

        temperature = base_temp + np.random.normal(0, 1.1, len(timestamps))
        humidity = np.clip(humidity + np.random.normal(0, 4.5, len(timestamps)), 35, 98)

        conditions = np.where(
            rainfall > 3.5,
            "Thunderstorm",
            np.where(rainfall > 1.1, "Rain", np.where(humidity > 82, "Clouds", np.where(temperature > 31, "Clear", "Haze"))),
        )

        return pd.DataFrame(
            {
                "timestamp": timestamps,
                "temperature": np.round(temperature, 2),
                "humidity": np.round(humidity, 2),
                "rainfall": np.round(rainfall, 2),
                "wind_speed": np.round(wind_speed, 2),
                "weather_condition": conditions,
                "weather_source": "synthetic",
            }
        )

    def area_weather_frame(self, timestamps: pd.DatetimeIndex) -> dict[str, pd.DataFrame]:
        weather_frames: dict[str, pd.DataFrame] = {}
        for area in AREA_COORDINATES:
            weather_frames[area] = self.synthetic_hourly_weather(timestamps, area)
        return weather_frames

    def current_area_weather(self) -> list[dict[str, Any]]:
        snapshots: list[dict[str, Any]] = []
        now = pd.Timestamp.utcnow().tz_localize(None).floor("h")
        for area, (latitude, longitude) in AREA_COORDINATES.items():
            try:
                live = self.fetch_live_weather(latitude, longitude)
                payload = {
                    "area": area,
                    "timestamp": now.isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    **live.__dict__,
                }
            except Exception:
                fallback = self.synthetic_hourly_weather(pd.date_range(now, periods=1, freq="h"), area).iloc[0].to_dict()
                payload = {
                    "area": area,
                    "timestamp": now.isoformat(),
                    "latitude": latitude,
                    "longitude": longitude,
                    "temperature": float(fallback["temperature"]),
                    "humidity": float(fallback["humidity"]),
                    "rainfall": float(fallback["rainfall"]),
                    "wind_speed": float(fallback["wind_speed"]),
                    "weather_condition": str(fallback["weather_condition"]),
                    "source": "synthetic",
                }
            snapshots.append(payload)
        return snapshots
