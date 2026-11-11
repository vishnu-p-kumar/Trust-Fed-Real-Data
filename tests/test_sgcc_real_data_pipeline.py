from __future__ import annotations
import numpy as np
import pandas as pd
from scripts.prepare_sgcc_dataset import build_features
from src.ceew_dataset import _source_location
from pathlib import Path

def test_sgcc_feature_builder_creates_one_customer_row_and_preserves_labels(tmp_path):
    dates = pd.date_range("2014-01-01", periods=365, freq="D")
    data = {"CONS_NO": [f"C{i}" for i in range(8)], "FLAG": [0,1,0,1,0,1,0,1]}
    for j, date in enumerate(dates):
        data[f"{date.year}/{date.month}/{date.day}"] = [float(i + j % 20) for i in range(8)]
    frame = pd.DataFrame(data)
    frame.loc[0, "2014/1/1"] = np.nan
    source = tmp_path / "sgcc.csv"
    frame.to_csv(source, index=False)
    features, manifest = build_features(source)
    assert len(features) == 8
    assert features["meter_id"].is_unique
    assert features["is_theft"].sum() == 4
    assert "missing_rate" in features
    assert manifest["daily_columns"] == 365

def test_ceew_short_city_codes_resolve_for_aggregated_files():
    assert _source_location(Path("SM Cleaned Data BR2019.csv")) == "Bareilly"
    assert _source_location(Path("SM Cleaned Data MH Aggregated.csv")) == "Mathura"


def test_federated_experiment_handles_missing_meter_readings_without_zero_imputation():
    from src.federated.experiment import run_experiment
    rng = np.random.default_rng(44)
    n = 180
    y = np.array([0, 1] * (n // 2))
    frame = pd.DataFrame({
        "meter_id": [f"M{i:04d}" for i in range(n)],
        "is_theft": y,
        "daily_1": y + rng.normal(0, 1, n),
        "daily_2": rng.normal(0, 1, n),
        "daily_3": rng.normal(0, 1, n),
    })
    frame.loc[::7, "daily_1"] = np.nan
    result = run_experiment({"seed": 5, "clients": 3, "rounds": 1,
        "local_epochs": 1, "batch_size": 16, "samples": n, "features": 3,
        "partition": "moderate", "malicious_fraction": 0.0}, dataframe=frame)
    assert result["split"]["strategy"] == "customer_group_holdout"
    assert result["split"]["test_group_overlap"] is False
    assert all(0 <= result["metrics"][name]["accuracy"] <= 1
               for name in ("fedavg", "hatta", "centralized"))


def test_zip_recovery_extracts_only_crc_valid_members(tmp_path):
    import zipfile
    from scripts.recover_ceew_zip import recover
    archive = tmp_path / "archive.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("sample.csv", "meter,date,kwh\\nM1,2020-01-01,1.2\\n")
    output = tmp_path / "recovered"
    report = recover(archive, output)
    assert len(report["recovered"]) == 1
    assert not report["skipped"]
    assert (output / "sample.csv").read_text().startswith("meter,date,kwh")
