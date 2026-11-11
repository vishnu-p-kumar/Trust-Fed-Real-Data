"""Validate a candidate labeled electricity-theft CSV before it enters experiments.

No independently verified Indian theft labels are bundled with GridSentinel. This tool
requires the user to provide a source file and provenance manifest; it cannot prove the
truth of labels, which must be confirmed with the data provider / inspection records.
"""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import pandas as pd

LABEL_ALIASES = ("is_theft", "theft_label", "label", "target", "fraud", "flag")
ID_ALIASES = ("meter_id", "customer_id", "consumer_id", "client_id", "cons_no", "consno", "consumerid", "customer", "id")


def validate(path: Path, manifest_path: Path | None = None) -> dict:
    if not path.is_file():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path, low_memory=False)
    cols = {str(column).strip().lower(): column for column in frame.columns}
    label = next((cols[name] for name in LABEL_ALIASES if name in cols), None)
    meter = next((cols[name] for name in ID_ALIASES if name in cols), None)
    if label is None:
        raise ValueError("No recognized label column found; unlabeled consumption data cannot validate theft classification.")
    if meter is None:
        raise ValueError("No recognized meter/customer identifier found; customer-disjoint evaluation is not possible.")
    labels = frame[label].dropna()
    unique = sorted(map(str, labels.unique().tolist()))
    if len(unique) != 2:
        raise ValueError(f"Expected binary labels, found {len(unique)} unique values: {unique[:10]}")
    manifest = {}
    if manifest_path:
        if not manifest_path.is_file():
            raise ValueError(f"Provenance manifest does not exist: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required = ("source_name", "source_url", "license", "label_provenance", "label_verification")
    missing = [key for key in required if not str(manifest.get(key, "")).strip()]
    if missing:
        raise ValueError("Provenance manifest missing required fields: " + ", ".join(missing))
    return {
        "file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "rows": int(len(frame)), "columns": int(len(frame.columns)),
        "meter_column": str(meter), "label_column": str(label), "labels": unique,
        "missing_label_rows": int(frame[label].isna().sum()),
        "unique_meters": int(frame[meter].nunique(dropna=True)),
        "provenance": manifest,
        "caveat": "Structural validation does not independently verify the truth of labels. Confirm against utility inspection/audit records.",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path, help="JSON with source_name, source_url, license, label_provenance, label_verification")
    parser.add_argument("--output", type=Path, default=Path("reports/dataset_validation.json"))
    args = parser.parse_args()
    report = validate(args.input, args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
