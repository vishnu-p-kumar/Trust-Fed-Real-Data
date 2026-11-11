from __future__ import annotations

import json
import random
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

try:
    import joblib
except ImportError:  # pragma: no cover - handled at runtime
    joblib = None


AREA_COORDINATES: dict[str, tuple[float, float]] = {
    "Whitefield": (12.9698, 77.7499),
    "Electronic City": (12.8452, 77.6602),
    "Indiranagar": (12.9784, 77.6408),
    "Koramangala": (12.9279, 77.6271),
    "Marathahalli": (12.9591, 77.6974),
    "Yelahanka": (13.1005, 77.5963),
    "BTM Layout": (12.9166, 77.6101),
    "Jayanagar": (12.9250, 77.5938),
    "Malleshwaram": (13.0031, 77.5690),
    "Rajajinagar": (12.9911, 77.5533),
    "Hebbal": (13.0358, 77.5970),
    "Bellandur": (12.9279, 77.6762),
    "HSR Layout": (12.9116, 77.6474),
    "Banashankari": (12.9255, 77.5468),
    "Peenya Industrial Area": (13.0329, 77.5273),
}

BENGALURU_BOUNDS = {
    "latitude": (12.80, 13.20),
    "longitude": (77.45, 77.80),
}

BASE_FEATURE_COLUMNS = [
    "voltage",
    "current",
    "power",
    "consumption_kwh",
    "power_factor",
    "temperature",
    "humidity",
    "rainfall",
    "wind_speed",
    "hour_of_day",
    "day_of_week",
    "rolling_average_consumption",
    "consumption_variance",
    "peak_usage_ratio",
    "night_usage_ratio",
    "weather_consumption_ratio",
    "power_factor_loss",
    "voltage_irregularity",
    "current_power_gap",
]

CATEGORICAL_COLUMNS = ["region", "area", "weather_condition", "usage_profile"]


@dataclass(frozen=True)
class ProjectPaths:
    root: Path
    data_raw: Path
    data_processed: Path
    dataset: Path
    live_dataset: Path
    meter_catalog: Path
    pole_catalog: Path
    model_dir: Path
    isolation_forest: Path
    random_forest: Path
    xgboost_model: Path
    lstm_model: Path
    transformer_model: Path
    model_metadata: Path
    demand_metadata: Path
    transformer_metadata: Path
    optimizer_params: Path
    api_dir: Path
    dashboard_dir: Path
    map_path: Path
    database: Path
    reports_dir: Path
    drift_report: Path
    daily_report: Path


def project_paths() -> ProjectPaths:
    root = Path(__file__).resolve().parents[1]
    return ProjectPaths(
        root=root,
        data_raw=root / "data" / "raw",
        data_processed=root / "data" / "processed",
        dataset=root / "dataset" / "smart_meter_data.csv",
        live_dataset=root / "data" / "processed" / "live_simulation.csv",
        meter_catalog=root / "data" / "processed" / "meter_catalog.csv",
        pole_catalog=root / "data" / "processed" / "pole_catalog.csv",
        model_dir=root / "models",
        isolation_forest=root / "models" / "isolation_forest.pkl",
        random_forest=root / "models" / "random_forest.pkl",
        xgboost_model=root / "models" / "xgboost_model.pkl",
        lstm_model=root / "models" / "lstm_model.h5",
        transformer_model=root / "models" / "transformer_forecaster.pt",
        model_metadata=root / "models" / "model_metadata.json",
        demand_metadata=root / "models" / "demand_metadata.json",
        transformer_metadata=root / "models" / "transformer_metadata.json",
        optimizer_params=root / "models" / "optimizer_best_params.json",
        api_dir=root / "api",
        dashboard_dir=root / "dashboard",
        map_path=root / "maps" / "theft_heatmap.html",
        database=root / "database" / "meter_data.db",
        reports_dir=root / "reports",
        drift_report=root / "reports" / "drift_report.json",
        daily_report=root / "reports" / "daily_energy_report.pdf",
    )


def ensure_project_dirs(paths: ProjectPaths | None = None) -> ProjectPaths:
    paths = paths or project_paths()
    directories = [
        paths.root,
        paths.data_raw,
        paths.data_processed,
        paths.dataset.parent,
        paths.model_dir,
        paths.api_dir,
        paths.dashboard_dir,
        paths.map_path.parent,
        paths.database.parent,
        paths.reports_dir,
    ]
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    return paths


def seed_everything(seed: int = 42) -> None:
    random.seed(seed)
    np.random.seed(seed)


def generation_config(full_scale: bool = False) -> dict[str, Any]:
    if full_scale:
        return {
            "num_meters": 1000,
            "days": 365,
            "chunk_size": 100,
            "sample_rows": 120000,
            "simulation_days": 14,
            "simulation_meter_limit": 80,
            "seed": 42,
        }
    return {
        "num_meters": 500,
        "days": 60,
        "chunk_size": 45,
        "sample_rows": 45000,
        "simulation_days": 10,
        "simulation_meter_limit": 425,
        "seed": 42,
    }


def jitter_coordinate(latitude: float, longitude: float, scale: float = 0.012) -> tuple[float, float]:
    lat = float(np.clip(latitude + np.random.normal(0, scale), *BENGALURU_BOUNDS["latitude"]))
    lon = float(np.clip(longitude + np.random.normal(0, scale), *BENGALURU_BOUNDS["longitude"]))
    return lat, lon


def save_json(payload: Any, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    serialisable = to_builtin(payload)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(serialisable, handle, indent=2)


def load_json(path: str | Path, default: Any | None = None) -> Any:
    target = Path(path)
    if not target.exists():
        return default
    with target.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_joblib(model: Any, path: str | Path) -> None:
    if joblib is None:
        raise RuntimeError("joblib is required to persist model artifacts.")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, target)


def load_joblib(path: str | Path) -> Any:
    if joblib is None:
        raise RuntimeError("joblib is required to load model artifacts.")
    return joblib.load(Path(path))


def sqlite_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    paths = ensure_project_dirs()
    target = Path(db_path) if db_path else paths.database
    target.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(target)


def dataframe_to_sqlite(
    dataframe: pd.DataFrame,
    table_name: str,
    if_exists: str = "replace",
    db_path: str | Path | None = None,
) -> None:
    connection = sqlite_connection(db_path)
    try:
        # Append operations must tolerate databases created by older project versions.
        # SQLite's pandas ``if_exists="append"`` does not add columns automatically.
        # Add newly introduced columns before inserting, preserving existing history.
        if if_exists == "append":
            table_exists = connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                (table_name,),
            ).fetchone()
            if table_exists:
                existing_columns = {
                    row[1] for row in connection.execute(
                        f'PRAGMA table_info("{table_name}")'
                    ).fetchall()
                }
                for column in dataframe.columns:
                    if column not in existing_columns:
                        dtype = dataframe[column].dtype
                        if pd.api.types.is_bool_dtype(dtype) or pd.api.types.is_integer_dtype(dtype):
                            sql_type = "INTEGER"
                        elif pd.api.types.is_float_dtype(dtype):
                            sql_type = "REAL"
                        else:
                            sql_type = "TEXT"
                        safe_column = str(column).replace('"', '""')
                        connection.execute(
                            f'ALTER TABLE "{table_name}" ADD COLUMN "{safe_column}" {sql_type}'
                        )
        dataframe.to_sql(table_name, connection, index=False, if_exists=if_exists)
        connection.commit()
    finally:
        connection.close()


def query_sqlite(query: str, db_path: str | Path | None = None) -> pd.DataFrame:
    connection = sqlite_connection(db_path)
    try:
        return pd.read_sql_query(query, connection)
    finally:
        connection.close()


def to_builtin(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_builtin(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return to_builtin(asdict(value))
    # last-resort fallback: convert other non-primitive objects to string so
    # json.dump doesn't choke on things like evidently.column_type.ColumnType
    # which appear in drift reports. This keeps the output readable.
    if not isinstance(value, (str, int, float, bool, type(None))):
        try:
            return str(value)
        except Exception:
            pass
    return value


def records_for_json(dataframe: pd.DataFrame, limit: int | None = None) -> list[dict[str, Any]]:
    if dataframe.empty:
        return []
    frame = dataframe.copy()
    if limit is not None:
        frame = frame.head(limit)
    for column in frame.columns:
        if pd.api.types.is_datetime64_any_dtype(frame[column]):
            frame[column] = frame[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return frame.replace({np.nan: None}).to_dict(orient="records")


def latest_rows_by_meter(dataframe: pd.DataFrame, limit: int = 25) -> pd.DataFrame:
    if dataframe.empty:
        return dataframe
    return (
        dataframe.sort_values(["meter_id", "timestamp"])
        .groupby("meter_id", as_index=False)
        .tail(1)
        .sort_values("timestamp", ascending=False)
        .head(limit)
        .reset_index(drop=True)
    )


def metric_round(value: Any, digits: int = 4) -> Any:
    if value is None:
        return None
    if isinstance(value, (float, np.floating)):
        return round(float(value), digits)
    return value


def summarise_generation(
    dataframe: pd.DataFrame,
    meter_catalog: pd.DataFrame,
) -> dict[str, Any]:
    return {
        "records": int(len(dataframe)),
        "meters": int(meter_catalog["meter_id"].nunique()) if not meter_catalog.empty else 0,
        "areas": sorted(meter_catalog["area"].unique().tolist()) if not meter_catalog.empty else [],
        "theft_rate": metric_round(dataframe["is_theft"].mean()) if "is_theft" in dataframe else 0.0,
        "wastage_rate": metric_round((dataframe.get("wastage_score", pd.Series(dtype=float)) > 0.25).mean())
        if "wastage_score" in dataframe
        else 0.0,
    }


def chunked(items: Iterable[Any], size: int) -> Iterable[list[Any]]:
    bucket: list[Any] = []
    for item in items:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket
