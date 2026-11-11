"""Streaming ingestion for the CEEW Mathura/Bareilly smart-meter files.

The source files contain consumption measurements, not verified theft labels.
Raw inputs are read-only; normalized chunks and a provenance manifest are
written under a caller-selected output directory.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

CEEW_DATASET_DOI = "https://doi.org/10.7910/DVN/GOCHJH"
_ALIASES = {
    "timestamp": {"xtimestamp", "timestamp", "datetime", "date", "time"},
    "meter_id": {"meter", "meterid", "meter_id"},
    "consumption_kwh": {"tkwh", "kwh", "consumptionkwh", "consumption"},
    "voltage_v": {"zavgvoltagevolt", "avgvoltagevolt", "voltagev", "voltage"},
    "current_a": {"zavgcurrentamp", "avgcurrentamp", "currenta", "current"},
    "frequency_hz": {"yfreqhz", "frequencyhz", "frequency"},
}
_REQUIRED = {"timestamp", "meter_id", "consumption_kwh"}


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).strip().lower())


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _column_map(columns: Iterable[Any], mode: str) -> dict[str, Any]:
    aliases = dict(_ALIASES)
    if mode == "daily_aggregate":
        aliases["timestamp"] = {"date", "timestamp", "datetime"}
    found: dict[str, Any] = {}
    for canonical, names in aliases.items():
        matches = [col for col in columns if _norm(col) in names]
        if matches:
            if len(matches) != 1:
                raise ValueError(f"ambiguous {canonical} columns: {matches}")
            found[canonical] = matches[0]
    missing = sorted(_REQUIRED.difference(found))
    if missing:
        raise ValueError(f"missing required CEEW columns: {missing}; received {list(columns)}")
    if mode == "high_frequency" and not {"voltage_v", "current_a", "frequency_hz"}.issubset(found):
        raise ValueError("high_frequency mode requires voltage, current, and frequency columns")
    if mode == "daily_aggregate" and any(k in found for k in ("voltage_v", "current_a", "frequency_hz")):
        raise ValueError("daily_aggregate mode accepts daily consumption fields only")
    return found


def _source_location(path: Path) -> str:
    name = path.stem.lower()
    if "bareilly" in name or re.search(r"\bbr(?:2019|2020|2021|19|20|21)?", name):
        return "Bareilly"
    if "mathura" in name or re.search(r"\bmh(?:2019|2020|2021|19|20|21)?", name):
        return "Mathura"
    return "unspecified"


def ingest_ceew_files(
    files: Iterable[str | Path],
    output_dir: str | Path,
    *,
    mode: str = "auto",
    chunksize: int = 100_000,
    max_rows_per_file: int | None = None,
    write_normalized: bool = True,
) -> dict[str, Any]:
    """Normalize one or more source files in chunks and save a quality manifest.

    ``mode='auto'`` identifies the documented interval versus daily schema from
    headers. Duplicate readings are retained; counts below are exact within
    each chunk and include adjacent chunk boundaries, not a global dedup pass.
    """
    if mode not in {"auto", "high_frequency", "daily_aggregate"}:
        raise ValueError("mode must be auto, high_frequency, or daily_aggregate")
    if chunksize < 1 or (max_rows_per_file is not None and max_rows_per_file < 1):
        raise ValueError("chunksize and max_rows_per_file must be positive")
    paths = [Path(item) for item in files]
    if not paths:
        raise ValueError("at least one CEEW input file is required")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"CEEW input file not found: {path}")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    reports: list[dict[str, Any]] = []
    meter_union_by_location: dict[str, set[str]] = {}
    for source in paths:
        if source.suffix.lower() not in {".csv", ".tsv", ".tab"}:
            raise ValueError(f"unsupported CEEW file format: {source.suffix}")
        sep = "\t" if source.suffix.lower() in {".tsv", ".tab"} else ","
        header = pd.read_csv(source, sep=sep, nrows=0).columns
        selected_mode = mode
        if selected_mode == "auto":
            normalized = {_norm(col) for col in header}
            selected_mode = "high_frequency" if "xtimestamp" in normalized else "daily_aggregate"
        mapping = _column_map(header, selected_mode)
        location = _source_location(source)
        meter_union_by_location.setdefault(location, set())
        out_path: Path | None = None
        if write_normalized:
            out_subdir = root / selected_mode
            out_subdir.mkdir(parents=True, exist_ok=True)
            out_path = out_subdir / f"{source.stem}.normalized.csv.gz"
            if out_path.exists():
                out_path.unlink()

        meters: set[str] = set()
        missing = Counter()
        invalid_numeric = Counter()
        negative = Counter()
        zero_by_field = Counter()
        minimum_by_field: dict[str, float] = {}
        maximum_by_field: dict[str, float] = {}
        absent_optional_fields = [field for field in ("voltage_v", "current_a", "frequency_hz") if field not in mapping]
        zero_readings = 0
        duplicate_keys_within_chunks = 0
        duplicate_rows_across_boundary = 0
        previous_chunk_last: dict[str, pd.Timestamp] = {}
        interval_seconds = Counter()
        nonpositive_time_steps = 0
        out_of_order_time_steps = 0
        first_timestamp: pd.Timestamp | None = None
        last_timestamp: pd.Timestamp | None = None
        rows = 0
        valid_timestamp_rows = 0
        invalid_meter_rows = 0
        mode_str = "wt"
        for chunk in pd.read_csv(source, sep=sep, chunksize=chunksize, low_memory=False):
            if max_rows_per_file is not None:
                chunk = chunk.iloc[: max(0, max_rows_per_file - rows)]
                if chunk.empty:
                    break
            normalized = pd.DataFrame(index=chunk.index)
            normalized["meter_id"] = chunk[mapping["meter_id"]].astype("string").str.strip()
            normalized.loc[normalized["meter_id"].eq(""), "meter_id"] = pd.NA
            normalized["timestamp"] = pd.to_datetime(chunk[mapping["timestamp"]], errors="coerce")
            normalized["consumption_kwh"] = pd.to_numeric(chunk[mapping["consumption_kwh"]], errors="coerce")
            for field in ("voltage_v", "current_a", "frequency_hz"):
                if field in mapping:
                    normalized[field] = pd.to_numeric(chunk[mapping[field]], errors="coerce")
                else:
                    normalized[field] = np.nan
            for field in ("consumption_kwh", "voltage_v", "current_a", "frequency_hz"):
                vals = normalized[field].to_numpy(dtype=float)
                finite = np.isfinite(vals)
                invalid_numeric[field] += int((chunk[mapping[field]].notna() & normalized[field].isna()).sum()) if field in mapping else 0
                invalid_numeric[field] += int((~finite & ~np.isnan(vals)).sum())
                normalized.loc[~finite, field] = np.nan
                if field in mapping:
                    missing[field] += int(normalized[field].isna().sum())
            for field in ("consumption_kwh", "voltage_v", "current_a", "frequency_hz"):
                if field in mapping:
                    finite_values = normalized[field].dropna()
                    negative[field] += int((finite_values < 0).sum())
                    zero_by_field[field] += int((finite_values == 0).sum())
                    if not finite_values.empty:
                        local_min, local_max = float(finite_values.min()), float(finite_values.max())
                        minimum_by_field[field] = min(minimum_by_field.get(field, local_min), local_min)
                        maximum_by_field[field] = max(maximum_by_field.get(field, local_max), local_max)
            zero_readings += int((normalized["consumption_kwh"] == 0).sum())
            valid_timestamp_rows += int(normalized["timestamp"].notna().sum())
            invalid_meter_rows += int(normalized["meter_id"].isna().sum())
            meters.update(normalized["meter_id"].dropna().astype(str).unique())

            keys = normalized.loc[normalized["timestamp"].notna() & normalized["meter_id"].notna(), ["meter_id", "timestamp"]]
            duplicate_keys_within_chunks += int(keys.duplicated(keep="first").sum())
            if not keys.empty:
                for meter, series in keys.groupby("meter_id", sort=False)["timestamp"]:
                    timestamps = series.to_list()
                    prior = previous_chunk_last.get(str(meter))
                    adjacent = ([prior] if prior is not None else []) + timestamps
                    if len(adjacent) > 1:
                        differences = pd.Series(adjacent).diff().dt.total_seconds().dropna().astype(int)
                        for seconds in differences:
                            if seconds <= 0:
                                nonpositive_time_steps += 1
                                out_of_order_time_steps += int(seconds < 0)
                            else:
                                interval_seconds[int(seconds)] += 1
                first_rows = keys.drop_duplicates("meter_id", keep="first")
                for row in first_rows.itertuples(index=False):
                    prior = previous_chunk_last.get(str(row.meter_id))
                    if prior is not None and row.timestamp <= prior:
                        duplicate_rows_across_boundary += int(row.timestamp == prior)
                last_rows = keys.drop_duplicates("meter_id", keep="last")
                previous_chunk_last.update({str(row.meter_id): row.timestamp for row in last_rows.itertuples(index=False)})
            stamps = normalized["timestamp"].dropna()
            if not stamps.empty:
                local_min, local_max = stamps.min(), stamps.max()
                first_timestamp = local_min if first_timestamp is None else min(first_timestamp, local_min)
                last_timestamp = local_max if last_timestamp is None else max(last_timestamp, local_max)
            normalized["location"] = location
            normalized["resolution"] = "3min" if selected_mode == "high_frequency" else "daily"
            normalized["source_file"] = source.name
            normalized["source_row"] = np.arange(rows + 1, rows + len(normalized) + 1, dtype=np.int64)
            if out_path is not None:
                normalized.to_csv(out_path, index=False, mode=mode_str, header=(mode_str == "wt"), compression="gzip", date_format="%Y-%m-%dT%H:%M:%S")
                mode_str = "at"
            rows += len(normalized)

        reports.append({
            "source_file": source.name,
            "source_sha256": _sha256(source),
            "mode": selected_mode,
            "location": location,
            "output_file": str(out_path.relative_to(root)) if out_path is not None else None,
            "row_count_processed": rows,
            "is_complete_source": max_rows_per_file is None,
            "meter_count": len(meters),
            "timestamp_start": first_timestamp.isoformat() if first_timestamp is not None else None,
            "timestamp_end": last_timestamp.isoformat() if last_timestamp is not None else None,
            "observed_positive_intervals_seconds_top20": {str(k): int(v) for k, v in interval_seconds.most_common(20)},
            "nonpositive_timestamp_steps": nonpositive_time_steps,
            "out_of_order_timestamp_steps": out_of_order_time_steps,
            "valid_timestamp_rows": valid_timestamp_rows,
            "invalid_meter_rows": invalid_meter_rows,
            "missing_by_field": dict(missing),
            "invalid_numeric_by_field": dict(invalid_numeric),
            "optional_fields_absent_from_source": absent_optional_fields,
            "negative_readings_by_field": dict(negative),
            "zero_readings_by_field": dict(zero_by_field),
            "minimum_by_field": minimum_by_field,
            "maximum_by_field": maximum_by_field,
            "zero_consumption_rows": zero_readings,
            "duplicate_key_rows_within_chunks": duplicate_keys_within_chunks,
            "duplicate_key_rows_at_chunk_boundaries": duplicate_rows_across_boundary,
            "duplicate_detection_note": "duplicates are retained; within-chunk and adjacent-boundary counts only, not a global deduplication scan",
        })
        meter_union_by_location[location].update(meters)

    manifest: dict[str, Any] = {
        "dataset": "CEEW high-frequency smart meter data from Mathura and Bareilly",
        "dataset_doi": CEEW_DATASET_DOI,
        "task_scope": "real consumption/supply observations; no theft ground-truth label column is present",
        "mode": mode,
        "chunk_size": chunksize,
        "max_rows_per_file": max_rows_per_file,
        "normalized_files_written": write_normalized,
        "files": reports,
        "distinct_meter_count_by_location": {location: len(values) for location, values in meter_union_by_location.items()},
        "license": "Harvard Dataverse record reports CC0 1.0; cite dataset DOI and verify the exact acquired version metadata",
        "preprocessing": "canonical columns, parsed timestamps, numeric coercion with invalid/missing values preserved as null, all rows retained, no imputation or synthetic labels",
    }
    manifest_path = root / "ceew_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

