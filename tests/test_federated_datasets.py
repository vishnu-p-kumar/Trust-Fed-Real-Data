from __future__ import annotations

import json

import pandas as pd
import pytest

from src.federated.datasets import load_sgcc_csv
from src.federated.experiment import run_experiment


def _wide_fixture() -> pd.DataFrame:
    return pd.DataFrame({
        "CONS_NO": [f"m{i}" for i in range(6)],
        "FLAG": [0, 0, 0, 0, 1, 1],
        "2014/1/2": [2.0, 3.0, None, 5.0, 1.0, 0.5],
        "2014/1/1": [1.0, 2.0, 3.0, 4.0, 0.5, 0.2],
    })


def test_load_sgcc_csv_sorts_dates_preserves_missing_and_writes_provenance(tmp_path) -> None:
    source = tmp_path / "sgcc_fixture.csv"
    manifest = tmp_path / "manifest.json"
    _wide_fixture().to_csv(source, index=False)

    frame, provenance = load_sgcc_csv(source, manifest_path=manifest)

    assert frame.columns.tolist() == ["meter_id", "is_theft", "2014-01-01", "2014-01-02"]
    assert frame["meter_id"].is_unique
    assert frame["is_theft"].tolist() == [0, 0, 0, 0, 1, 1]
    assert pd.isna(frame.loc[2, "2014-01-02"])
    assert provenance["meter_count"] == 6
    assert provenance["missing_consumption_cells"] == 1
    assert json.loads(manifest.read_text(encoding="utf-8"))["source_sha256"] == provenance["source_sha256"]


def test_load_sgcc_csv_accepts_separate_labels_by_meter_id(tmp_path) -> None:
    data_path = tmp_path / "data.csv"
    labels_path = tmp_path / "labels.csv"
    data = _wide_fixture().drop(columns="FLAG")
    data.to_csv(data_path, index=False)
    pd.DataFrame({"CONS_NO": [f"m{i}" for i in range(6)], "FLAG": [0, 0, 0, 0, 1, 1]}).to_csv(labels_path, index=False)

    frame, provenance = load_sgcc_csv(data_path, labels_path=labels_path)

    assert frame["is_theft"].tolist() == [0, 0, 0, 0, 1, 1]
    assert provenance["labels_sha256"]


def test_load_sgcc_csv_rejects_missing_data_instead_of_falling_back(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="No synthetic fallback"):
        load_sgcc_csv(tmp_path / "absent.csv")


def test_load_sgcc_csv_rejects_duplicate_meter_ids_and_bad_hash(tmp_path) -> None:
    source = tmp_path / "bad.csv"
    frame = _wide_fixture()
    frame.loc[1, "CONS_NO"] = "m0"
    frame.to_csv(source, index=False)
    with pytest.raises(ValueError, match="unique meter ID"):
        load_sgcc_csv(source)
    with pytest.raises(ValueError, match="SHA-256"):
        load_sgcc_csv(source, expected_sha256="0" * 64)


def test_loaded_sgcc_data_runs_with_meter_disjoint_validation_and_test(tmp_path) -> None:
    source = tmp_path / "sgcc_grouped.csv"
    data = pd.DataFrame({
        "CONS_NO":[f"m{i}" for i in range(10)],
        "FLAG":[0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
        "2014-01-01":[1., 2., 1.2, 2.2, 1.4, 2.4, .2, .3, .4, .5],
        "2014-01-02":[1.1, 2.1, 1.3, 2.3, 1.5, 2.5, .1, .2, .3, .4],
    })
    data.to_csv(source, index=False)
    frame, _ = load_sgcc_csv(source)

    result = run_experiment({"clients":3,"rounds":1,"local_epochs":1,"partition":"iid","seed":19}, dataframe=frame)

    assert result["split"]["strategy"] == "customer_group_holdout"
    assert result["split"]["test_group_overlap"] is False
    assert result["split"]["validation_group_overlap"] is False
