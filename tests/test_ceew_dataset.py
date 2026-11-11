from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from src.ceew_dataset import _source_location, ingest_ceew_files
from src.federated.consumption_forecast import run_consumption_forecast
from src.federated.partition import partition_by_group


def test_ceew_stream_ingestion_normalizes_fields_and_preserves_unlabeled_data(tmp_path):
    source = tmp_path / "CEEW Smart meter data Mathura 2019.csv"
    pd.DataFrame({
        "x_Timestamp": ["2019-01-01 00:00:00", "2019-01-01 00:03:00", "2019-01-01 00:03:00", "bad"],
        "t_kWh": [0.8, 1.2, 1.2, "bad"],
        "z_Avg Voltage (Volt)": [241, 240, 240, 240],
        "z_Avg Current (Amp)": [2, 1, 1, 1],
        "y_Freq (Hz)": [50, 50, 50, 50],
        "meter": ["MH01", "MH01", "MH01", "MH01"],
    }).to_csv(source, index=False)
    report = ingest_ceew_files([source], tmp_path / "processed", chunksize=2)
    entry = report["files"][0]
    assert entry["row_count_processed"] == 4
    assert entry["meter_count"] == 1
    assert entry["valid_timestamp_rows"] == 3
    assert entry["minimum_by_field"]["consumption_kwh"] == .8
    assert entry["maximum_by_field"]["consumption_kwh"] == 1.2
    assert entry["zero_readings_by_field"]["consumption_kwh"] == 0
    assert entry["duplicate_key_rows_within_chunks"] + entry["duplicate_key_rows_at_chunk_boundaries"] == 1
    assert "no theft ground-truth label" in report["task_scope"]
    output = pd.read_csv(tmp_path / "processed" / entry["output_file"], compression="gzip")
    assert len(output) == 4  # invalid and duplicate records are retained and reported
    assert output["timestamp"].isna().sum() == 1
    assert set(["meter_id", "consumption_kwh", "voltage_v", "current_a", "frequency_hz"]).issubset(output.columns)
    assert json.loads((tmp_path / "processed" / "ceew_manifest.json").read_text())["files"][0]["source_sha256"]


def test_ceew_ingestion_rejects_unknown_schema_and_reports_partial_run(tmp_path):
    source = tmp_path / "unknown.csv"
    pd.DataFrame({"time": ["2020-01-01"], "reading": [1]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="missing required"):
        ingest_ceew_files([source], tmp_path / "bad")

    daily = tmp_path / "SM Cleaned Data BR Aggregated.csv"
    pd.DataFrame({"meter": ["BR01", "BR01"], "Date": ["2020-01-01", "2020-01-02"], "t_kWh": [1, 2]}).to_csv(daily, index=False)
    report = ingest_ceew_files([daily], tmp_path / "partial", max_rows_per_file=1)
    assert report["files"][0]["mode"] == "daily_aggregate"
    assert report["files"][0]["is_complete_source"] is False
    assert report["files"][0]["row_count_processed"] == 1


def test_meter_group_partition_is_disjoint_deterministic_and_complete():
    groups = np.repeat([f"meter-{i}" for i in range(8)], [1, 3, 2, 4, 1, 5, 2, 1])
    first = partition_by_group(groups, clients=4, seed=8)
    second = partition_by_group(groups, clients=4, seed=8)
    assert [p.indices.tolist() for p in first] == [p.indices.tolist() for p in second]
    assert sorted(np.concatenate([p.indices for p in first]).tolist()) == list(range(len(groups)))
    seen = set()
    for partition in first:
        meters = set(groups[partition.indices])
        assert not (seen & meters)
        seen.update(meters)
    assert len(seen) == len(np.unique(groups))


def test_ceew_location_infers_compact_historical_file_names():
    from pathlib import Path
    assert _source_location(Path("SM Cleaned Data BR2019.csv")) == "Bareilly"
    assert _source_location(Path("SM Cleaned Data MH2021.csv")) == "Mathura"


def test_ceew_tsv_daily_schema_is_detected_and_normalized(tmp_path):
    source = tmp_path / "daily.tsv"
    pd.DataFrame({"meter": ["M1", "M1"], "Date": ["2022-01-01", "2022-01-02"],
                  "t_kWh": [1.0, 1.2]}).to_csv(source, sep="\t", index=False)
    report = ingest_ceew_files([source], tmp_path / "tsv")
    assert report["files"][0]["mode"] == "daily_aggregate"
    assert report["files"][0]["row_count_processed"] == 2


def test_unlabeled_consumption_forecast_is_meter_partitioned_chronological_and_not_theft_detection():
    rows = []
    dates = pd.date_range("2020-01-01", periods=84, freq="D")
    for meter_index in range(8):
        for day_index, timestamp in enumerate(dates):
            value = 2 + meter_index * .4 + np.sin(day_index * 2 * np.pi / 7) + .01 * day_index
            rows.append({"meter_id": f"M{meter_index:02d}", "timestamp": timestamp,
                         "consumption_kwh": value, "location": "Bareilly" if meter_index < 4 else "Mathura"})
    rows.append(dict(rows[100]))  # one duplicate key is excluded and counted by the modeling step
    result = run_consumption_forecast(pd.DataFrame(rows), clients=4, rounds=2, local_epochs=3,
                                      learning_rate=.003, learning_rate_candidates=[.001, .003, .01],
                                      seed=7, interval="1D")
    assert result["label_status"].startswith("no verified theft labels")
    assert result["config"]["split"].startswith("per-meter chronological")
    assert result["counts"]["meters"] == 8
    assert result["quality"]["duplicate_key_rows_excluded"] == 1
    assert set(result["metrics"]) == {"validation", "test"}
    assert set(result["metrics"]["test"]) == {"centralized", "fedavg", "trimmed_mean", "local_only", "persistence"}
    assert result["forecast_residual_anomaly_proxy"]["threshold_kwh"] is not None
    assert result["forecast_residual_anomaly_proxy"]["test_rows"] > 0
    candidates = result["hyperparameter_selection"]["validation_candidates"]
    assert result["hyperparameter_selection"]["selected_learning_rate"] == min(
        candidates, key=lambda item: item["validation_mae_kwh"]
    )["learning_rate"]
    assert "malicious" not in json.dumps(result).lower()
    geographic = run_consumption_forecast(pd.DataFrame(rows), clients=2, rounds=2, local_epochs=3,
                                          learning_rate=.003, seed=7, interval="1D",
                                          client_partition="location")
    assert "non-IID geographic" in geographic["config"]["client_partition"]
    with pytest.raises(ValueError, match="location partition requires"):
        run_consumption_forecast(pd.DataFrame(rows).drop(columns="location"), clients=2,
                                 rounds=1, local_epochs=1, client_partition="location")

