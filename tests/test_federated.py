from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.federated.aggregators import fedavg, trimmed_mean, trust_weighted
from src.federated.experiment import _clip_update, run_calibrated_study, run_experiment
from src.federated.partition import partition_clients
from src.federated.trust import (normalized_weights, robust_validation_threshold,
                                 select_detection_threshold, update_trust, validation_harm)


def test_partition_is_deterministic_and_disjoint() -> None:
    y = np.tile([0, 1], 100)
    a = partition_clients(y, 5, "severe", 17)
    b = partition_clients(y, 5, "severe", 17)
    assert all(np.array_equal(x.indices, z.indices) for x, z in zip(a, b))
    assert sorted(np.concatenate([p.indices for p in a]).tolist()) == list(range(len(y)))


def test_fedavg_and_trust_weights_normalize() -> None:
    updates = [np.array([1., 3.]), np.array([3., 5.])]
    assert np.allclose(fedavg(updates, [1, 3]), [2.5, 4.5])
    assert np.allclose(trust_weighted(updates, [1, 1], [0.25, 0.75]), [2.5, 4.5])
    assert np.isclose(normalized_weights([.2, .8], [10, 10]).sum(), 1)
    assert np.allclose(trust_weighted(updates, [1, 3], [0, 0]), [2.5, 4.5])
    assert np.allclose(normalized_weights([0, 0], [1, 3]), [.25, .75])
    assert np.allclose(normalized_weights([1, 1], [10**300, 10**300]), [.5, .5])
    assert np.allclose(fedavg(updates, [10**300, 10**300]), [2., 4.])
    assert np.allclose(trust_weighted(updates, [10**300, 10**300], [1, 1]), [2., 4.])


def test_trimmed_mean_limits_single_extreme_update() -> None:
    values = [np.array([1.]), np.array([1.1]), np.array([.9]), np.array([100.])]
    assert trimmed_mean(values, .25)[0] < 2


def test_trust_recovers_without_majority_direction_penalty() -> None:
    score = update_trust(.2, .8, 1., .1)
    assert score > .2
    assert 0 <= score <= 1
    assert update_trust(.2, 0., 0., 0., recovery=.08) > update_trust(.2, 0., 0., 0., recovery=0.)


def test_validation_harm_and_robust_threshold_use_finite_validation_values() -> None:
    assert validation_harm(.7, .9) == pytest.approx(.2)
    assert validation_harm(.9, .7) == 0
    threshold = robust_validation_threshold([0.0, 0.0, 0.0, .5], 2.5)
    assert threshold == pytest.approx(1e-6)
    with pytest.raises(ValueError): robust_validation_threshold([.1, .2], 2.5)
    with pytest.raises(ValueError): update_trust(float("nan"), .5, .5, .5)


def test_detection_threshold_respects_calibration_false_accusation_constraint() -> None:
    scores = [.01, .02, .03, .50, .60]
    labels = [False, False, False, True, True]
    threshold = select_detection_threshold(scores, labels, max_false_accusation_rate=0.0)
    assert threshold == pytest.approx(.03)
    assert sum(score > threshold and not label for score, label in zip(scores, labels)) == 0
    assert sum(score > threshold and label for score, label in zip(scores, labels)) == 2


def test_calibrated_study_rejects_seed_overlap() -> None:
    with pytest.raises(ValueError, match="disjoint"):
        run_calibrated_study(calibration_seeds=[7], evaluation_seeds=[7])


def test_calibration_excludes_the_evaluation_attack_family_and_reports_ci() -> None:
    scenarios = [
        {"name":"benign_severe","attack":"none","malicious_fraction":0,"partition":"severe"},
        {"name":"benign_shift","attack":"none","malicious_fraction":0,"partition":"severe","benign_shift_strength":1.5},
        {"name":"sign_25","attack":"sign","malicious_fraction":.25,"partition":"severe"},
        {"name":"scale_25","attack":"scale","malicious_fraction":.25,"partition":"severe"},
    ]
    report = run_calibrated_study(calibration_seeds=[12, 13], evaluation_seeds=[22, 23],
        scenarios=scenarios, config={"samples":300,"features":8,"clients":3,"rounds":2,"local_epochs":1},
        evidence_ablations=("utility",))
    calibration = report["calibration"]["utility"]["sign_25"]
    assert "sign_25" not in calibration["calibration_scenarios"]
    assert calibration["excluded_attack_family"] == "sign"
    stats = report["scenarios"]["utility"]["sign_25"]["metric_statistics"]["hatta"]["f1"]
    assert stats["n"] == 2 and stats["std"] >= 0 and len(stats["ci95"]) == 2


def test_temporary_attack_records_stop_round_and_trust_recovery() -> None:
    result = run_experiment({"samples":300,"features":8,"clients":3,"rounds":3,"local_epochs":1,
        "partition":"severe","attack":"sign","malicious_fraction":.25,"attack_end_round":1,"seed":33})
    assert result["rounds"][0]["attacking_clients"]
    assert result["rounds"][1]["attacking_clients"] == []
    assert result["recovery"]["measured"] is True
    assert set(result["recovery"]["attacker_final_trust"]) == set(result["security"]["malicious_clients"])


def test_reproduced_sign_attack_is_detected_from_validation_harm() -> None:
    result = run_experiment({"samples": 400, "features": 10, "clients": 4, "rounds": 3, "local_epochs": 2,
                             "partition": "severe", "attack": "sign", "malicious_fraction": .25,
                             "attack_intensity": 4.0, "seed": 42})
    assert result["security"]["malicious_clients"] == ["client_000"]
    assert result["security"]["detection_recall"] == 1.0
    assert result["security"]["flagged_clients"] == ["client_000"]


def test_benign_non_iid_shift_is_recorded_without_identity_based_flags() -> None:
    result = run_experiment({"samples": 400, "features": 10, "clients": 4, "rounds": 3, "local_epochs": 2,
                             "partition": "severe", "attack": "none", "malicious_fraction": 0,
                             "benign_shift_strength": 1.5, "seed": 42})
    assert result["security"]["malicious_clients"] == []
    assert len(result["security"]["shifted_benign_clients"]) == 1
    assert len(result["security"]["flagged_clients"]) < result["config"]["clients"]


def test_small_experiment_emits_real_metrics_and_disabled_privacy(tmp_path) -> None:
    result = run_experiment({"samples": 300, "features": 8, "clients": 3, "rounds": 2, "local_epochs": 1,
                             "partition": "iid", "attack": "sign", "seed": 21}, output_dir=tmp_path)
    assert set(["centralized", "local_only", "fedavg", "trimmed_mean", "trust", "hatta"]).issubset(result["metrics"])
    assert result["privacy"]["enabled"] is False
    assert (tmp_path / "results.json").exists()


def test_experiment_uses_disjoint_meter_group_holdout() -> None:
    rng = np.random.default_rng(8)
    labels = np.repeat(np.tile([0, 1], 5), 40)
    frame = pd.DataFrame({"meter_id": np.repeat([f"m{i}" for i in range(10)], 40),
                          "signal": labels + rng.normal(0, .2, len(labels)), "is_theft": labels})
    result = run_experiment({"clients":3,"rounds":1,"local_epochs":1,"partition":"iid","seed":9}, dataframe=frame)
    assert result["split"] == {"strategy":"customer_group_holdout", "test_group_overlap":False,
                               "validation_group_overlap":False}
    assert result["metrics"]["fedavg"]["confusion_matrix"] and result["metrics"]["fedavg"]["n"] > 0


def test_aggregators_reject_invalid_updates() -> None:
    with pytest.raises(ValueError): fedavg([np.array([np.nan])], [1])
    with pytest.raises(ValueError): normalized_weights([np.nan], [1])
    with pytest.raises(ValueError): normalized_weights([.5, .5], [-1, 2])
    with pytest.raises(ValueError): fedavg([np.array([1.])], [0])
    clipped, _ = _clip_update(np.array([np.nan]), 1.0)
    assert clipped is None
    bounded, norm = _clip_update(np.array([3., 4.]), 2.0)
    assert np.isclose(norm, 5.0)
    assert np.isclose(np.linalg.norm(bounded), 2.0)
