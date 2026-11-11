from __future__ import annotations

import argparse
import math
import os
import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


ROOT = Path(__file__).resolve().parents[1]
AREAS = {
    "Whitefield": (12.9698, 77.7499),
    "Koramangala": (12.9279, 77.6271),
    "Electronic City": (12.8452, 77.6602),
}
ANOMALY_METER_NUMBERS = {5, 15, 25, 35, 45}


def load_local_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def meter_profile(index: int, seed: int) -> dict[str, object]:
    rng = random.Random(seed + index * 7919)
    pole_number = index // 10 + 1
    area = list(AREAS)[(pole_number - 1) % len(AREAS)]
    latitude, longitude = AREAS[area]
    return {
        "meter_id": f"SIM-MTR-{index + 1:04d}",
        "area": area,
        "latitude": latitude + rng.uniform(-0.003, 0.003),
        "longitude": longitude + rng.uniform(-0.003, 0.003),
        "daily_kwh": rng.uniform(4.5, 18.0),
        "power_factor": rng.uniform(0.78, 0.99),
        "voltage": rng.uniform(222.0, 239.0),
        "transformer_id": f"SIM-TX-{(pole_number - 1) // 10 + 1:02d}",
        "pole_id": f"SIM-POLE-{pole_number:04d}",
        "usage_profile": rng.choice(("residential", "residential", "commercial", "small_industry")),
        "anomaly_demo": index + 1 in ANOMALY_METER_NUMBERS,
        "seed": seed + index * 7919,
    }


def make_reading(profile: dict[str, object], timestamp: datetime, interval_seconds: int, *, daily_total: float | None = None) -> dict[str, object]:
    rng = random.Random(int(profile["seed"]) + int(timestamp.timestamp()))
    if profile["anomaly_demo"]:
        voltage = rng.uniform(170.0, 179.5)
        power_factor = rng.uniform(0.56, 0.64)
    else:
        voltage = max(205.0, min(252.0, float(profile["voltage"]) + rng.uniform(-4.0, 4.0)))
        power_factor = max(0.68, min(0.999, float(profile["power_factor"]) + rng.uniform(-0.025, 0.015)))
    if daily_total is None:
        hour = timestamp.astimezone(timezone.utc).hour
        daily_shape = 1.0 + 0.48 * math.cos((hour - 18.0) * 2.0 * math.pi / 24.0)
        power_kw = float(profile["daily_kwh"]) / 24.0 * daily_shape * rng.uniform(0.88, 1.12)
        consumption = power_kw * interval_seconds / 3600.0
    else:
        consumption = daily_total
        power_kw = daily_total / 24.0
    current = power_kw * 1000.0 / max(voltage * power_factor, 1.0)
    month = timestamp.month
    temperature = rng.uniform(21.0, 31.0) + (2.0 if month in (3, 4, 5) else 0.0)
    humidity = rng.uniform(42.0, 82.0)
    rainfall = rng.uniform(0.0, 3.5) if humidity > 67.0 else 0.0
    return {
        "meter_id": profile["meter_id"],
        "timestamp": timestamp.isoformat(),
        "consumption_kwh": round(consumption, 6),
        "voltage": round(voltage, 2),
        "current": round(current, 3),
        "power": round(power_kw, 4),
        "power_factor": round(power_factor, 3),
        "temperature": round(temperature, 1),
        "humidity": round(humidity, 1),
        "rainfall": round(rainfall, 2),
        "wind_speed": round(rng.uniform(0.0, 18.0), 1),
        "weather_condition": "rain" if rainfall > 0.4 else "cloudy" if humidity > 70 else "clear",
        "area": profile["area"],
        "region": "Bengaluru",
        "latitude": profile["latitude"],
        "longitude": profile["longitude"],
        "source": "synthetic_live_demo",
        "pole_id": profile["pole_id"],
        "transformer_id": profile["transformer_id"],
        "usage_profile": profile["usage_profile"],
    }


def post_batches(session: requests.Session, api_base: str, readings: list[dict[str, object]]) -> int:
    accepted = 0
    for offset in range(0, len(readings), 500):
        batch = readings[offset : offset + 500]
        response = session.post(f"{api_base}/api/telemetry/readings", json=batch, timeout=90)
        if response.status_code == 401:
            login(session, api_base)
            response = session.post(f"{api_base}/api/telemetry/readings", json=batch, timeout=90)
        if not response.ok:
            raise RuntimeError(f"Telemetry batch failed ({response.status_code}): {response.text[:1200]}")
        accepted += int(response.json().get("accepted_readings", len(batch)))
    return accepted


def login(session: requests.Session, api_base: str) -> None:
    email = os.getenv("SMARTGRID_ADMIN_EMAIL", "").strip()
    password = os.getenv("SMARTGRID_ADMIN_PASSWORD", "")
    if not email or not password:
        raise RuntimeError("Set SMARTGRID_ADMIN_EMAIL and SMARTGRID_ADMIN_PASSWORD in the local .env file.")
    response = session.post(
        f"{api_base}/auth/login",
        json={"identifier": email, "password": password},
        timeout=20,
    )
    response.raise_for_status()
    if response.json().get("role") != "admin":
        raise RuntimeError("The configured account did not authenticate as an administrator.")


def send_warmup(session: requests.Session, api_base: str, profiles: list[dict[str, object]], days: int) -> None:
    if days <= 0:
        return
    today = datetime.now(timezone.utc).date()
    history: list[dict[str, object]] = []
    for profile in profiles:
        rng = random.Random(int(profile["seed"]) + 1_000_003)
        for day_offset in range(days, 0, -1):
            day = today - timedelta(days=day_offset)
            weekday_factor = 0.91 if day.weekday() >= 5 else 1.0
            daily_total = float(profile["daily_kwh"]) * weekday_factor * rng.uniform(0.9, 1.1)
            timestamp = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=12)
            history.append(make_reading(profile, timestamp, 86400, daily_total=daily_total))
    total = post_batches(session, api_base, history)
    print(f"Synthetic warm-up sent: {total:,} daily readings across {len(profiles)} meters and {days} days.", flush=True)


def run() -> None:
    load_local_env()
    parser = argparse.ArgumentParser(description="Send clearly marked synthetic readings for a local 800-meter dashboard demo.")
    parser.add_argument("--api-base", default=os.getenv("SMARTGRID_API_BASE", "http://127.0.0.1:8000").rstrip("/"))
    parser.add_argument("--count", type=int, default=int(os.getenv("SMARTGRID_SYNTHETIC_METER_COUNT", "800")), help="Number of synthetic meters (default: 800).")
    parser.add_argument("--interval-seconds", type=int, default=int(os.getenv("SMARTGRID_SYNTHETIC_METER_INTERVAL_SECONDS", "300")), help="Seconds between fleet snapshots (default: 300).")
    parser.add_argument("--backfill-days", type=int, default=int(os.getenv("SMARTGRID_SYNTHETIC_METER_BACKFILL_DAYS", "30")), help="Synthetic daily warm-up for forecasts and the SGCC model (default: 30).")
    parser.add_argument("--seed", type=int, default=73021)
    parser.add_argument("--once", action="store_true", help="Send warm-up and one live snapshot, then exit.")
    args = parser.parse_args()
    if not 1 <= args.count <= 10000 or args.interval_seconds < 5 or not 0 <= args.backfill_days <= 365:
        parser.error("count must be 1–10000, interval-seconds at least 5, and backfill-days 0–365")

    profiles = [meter_profile(index, args.seed) for index in range(args.count)]
    api_base = args.api_base.rstrip("/")
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    for attempt in range(60):
        try:
            login(session, api_base)
            break
        except requests.ConnectionError:
            if attempt == 59:
                raise
            print("Waiting for the API to start before sending synthetic telemetry…", flush=True)
            time.sleep(5)
    print(f"Authenticated synthetic meter sender for {len(profiles)} meters at {api_base}.", flush=True)
    health_response = session.get(f"{api_base}/health", timeout=20)
    health_response.raise_for_status()
    health = health_response.json()
    existing_synthetic_meters = int(health.get("synthetic_telemetry_meters", 0))
    if args.backfill_days and existing_synthetic_meters < args.count:
        send_warmup(session, api_base, profiles, args.backfill_days)
    elif args.backfill_days:
        print(f"Synthetic warm-up already exists for {existing_synthetic_meters} meters; reusing it.", flush=True)

    while True:
        timestamp = datetime.now(timezone.utc).replace(microsecond=0)
        readings = [make_reading(profile, timestamp, args.interval_seconds) for profile in profiles]
        try:
            accepted = post_batches(session, api_base, readings)
            print(f"{timestamp.isoformat()} synthetic live readings accepted: {accepted:,}/{len(profiles):,}.", flush=True)
        except (requests.RequestException, RuntimeError) as error:
            print(f"{timestamp.isoformat()} sender will retry after an API error: {error}", flush=True)
        if args.once:
            break
        time.sleep(args.interval_seconds)


if __name__ == "__main__":
    run()
