from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

import pandas as pd


SGCC_REPOSITORY = "https://github.com/henryRDlab/ElectricityTheftDetection"
SGCC_CITATION = (
    "Z. Zheng, Y. Yang, X. Niu, H. Dai, and Y. Zhou, 'Wide and Deep Convolutional "
    "Neural Networks for Electricity-Theft Detection to Secure Smart Grids,' IEEE "
    "Transactions on Industrial Informatics, vol. 14, no. 4, pp. 1606-1615, 2018, "
    "doi:10.1109/TII.2017.2785963."
)

_ID_NAMES = {"consno", "consumerid", "customerid", "meterid", "userid", "id"}
_LABEL_NAMES = {"flag", "istheft", "theftlabel", "label"}


def _key(name: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(name).strip().lower())


def _find_column(columns: list[Any], accepted: set[str], role: str) -> Any:
    matches = [column for column in columns if _key(column) in accepted]
    if len(matches) != 1:
        raise ValueError(f"expected exactly one {role} column; found {matches}")
    return matches[0]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_sgcc_csv(
    csv_path: str | Path,
    *,
    labels_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load a locally acquired SGCC wide CSV without synthetic fallback.

    Input must contain one customer per row, customer ID, and daily columns
    with parseable date headers. Labels may be in that CSV or in a separate
    ID/FLAG CSV. Missing consumption values remain NaN for the experiment's
    fixed-zero imputation; this loader never imputes from the full dataset.
    """
    source = Path(csv_path)
    if not source.is_file():
        raise FileNotFoundError(f"SGCC input file not found: {source}. No synthetic fallback was used.")
    source_hash = _sha256(source)
    if expected_sha256 and source_hash.lower() != expected_sha256.lower():
        raise ValueError("SGCC input SHA-256 does not match expected_sha256")
    raw = pd.read_csv(source, low_memory=False)
    if raw.empty:
        raise ValueError("SGCC input CSV is empty")
    id_column = _find_column(list(raw.columns), _ID_NAMES, "meter ID")
    if raw[id_column].isna().any() or raw[id_column].astype(str).duplicated().any():
        raise ValueError("SGCC input must have one non-null row per unique meter ID")

    label_column = next((column for column in raw.columns if _key(column) in _LABEL_NAMES), None)
    labels_hash: str | None = None
    if labels_path is not None:
        label_source = Path(labels_path)
        if not label_source.is_file():
            raise FileNotFoundError(f"SGCC labels file not found: {label_source}. No synthetic fallback was used.")
        label_raw = pd.read_csv(label_source, low_memory=False)
        label_id = _find_column(list(label_raw.columns), _ID_NAMES, "label meter ID")
        label_name = _find_column(list(label_raw.columns), _LABEL_NAMES, "theft label")
        if label_raw[label_id].isna().any() or label_raw[label_id].astype(str).duplicated().any():
            raise ValueError("SGCC labels must have one non-null row per unique meter ID")
        if label_column is not None:
            raise ValueError("provide labels either in the data CSV or labels_path, not both")
        labels_hash = _sha256(label_source)
        label_frame = label_raw[[label_id, label_name]].copy()
        label_frame[label_id] = label_frame[label_id].astype(str)
        raw[id_column] = raw[id_column].astype(str)
        raw = raw.merge(label_frame, left_on=id_column, right_on=label_id, how="left", validate="one_to_one")
        if label_id != id_column:
            raw = raw.drop(columns=[label_id])
        label_column = label_name
        if raw[label_column].isna().any():
            raise ValueError("some SGCC meters have no matching label")
    elif label_column is None:
        raise ValueError("SGCC labels are missing; provide FLAG/is_theft or labels_path")

    labels = pd.to_numeric(raw[label_column], errors="coerce")
    if labels.isna().any() or not set(labels.unique()).issubset({0, 1}):
        raise ValueError("SGCC theft labels must be binary 0/1 values")

    excluded = {id_column, label_column}
    date_columns: list[tuple[pd.Timestamp, Any]] = []
    for column in raw.columns:
        if column in excluded:
            continue
        parsed = pd.to_datetime(str(column).strip(), errors="coerce")
        if not pd.isna(parsed):
            date_columns.append((pd.Timestamp(parsed), column))
    if len(date_columns) < 2:
        raise ValueError("SGCC wide CSV needs at least two daily columns with parseable date headers")
    date_columns.sort(key=lambda item: item[0])

    feature_names = [timestamp.strftime("%Y-%m-%d") for timestamp, _ in date_columns]
    if len(feature_names) != len(set(feature_names)):
        raise ValueError("duplicate daily consumption dates")
    numeric_profiles = raw[[original_name for _, original_name in date_columns]].apply(
        pd.to_numeric, errors="coerce"
    ).to_numpy(dtype="float32")
    frame = pd.DataFrame(numeric_profiles, columns=feature_names, copy=False)
    frame.insert(0, "is_theft", labels.astype("int8").to_numpy())
    frame.insert(0, "meter_id", raw[id_column].astype(str).to_numpy())

    counts = frame["is_theft"].value_counts().to_dict()
    provenance: dict[str, Any] = {
        "dataset": "SGCC electricity theft detection dataset",
        "source_repository": SGCC_REPOSITORY,
        "source_file": str(source.resolve()),
        "source_sha256": source_hash,
        "labels_file": str(Path(labels_path).resolve()) if labels_path else None,
        "labels_sha256": labels_hash,
        "row_count": int(len(frame)),
        "meter_count": int(frame["meter_id"].nunique()),
        "feature_count": len(feature_names),
        "date_start": feature_names[0],
        "date_end": feature_names[-1],
        "label_counts": {str(key): int(value) for key, value in counts.items()},
        "missing_consumption_cells": int(frame[feature_names].isna().sum().sum()),
        "features": feature_names,
        "preprocessing": "one row per unique meter; date columns sorted; values parsed numeric; missing cells retained as NaN",
        "split_requirement": "use meter_id for group-disjoint train/validation/test partitions",
        "citation": SGCC_CITATION,
        "license_note": "Upstream README requests citation; no explicit dataset license was identified in the inspected upstream repository. Verify terms for the acquired copy; this loader does not redistribute data.",
    }
    if manifest_path is not None:
        manifest = Path(manifest_path)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    return frame, provenance
