from __future__ import annotations

import numpy as np
import pytest

from src.federated.aggregators import multi_krum
from src.federated.checkpoint import load_checkpoint, save_checkpoint
from src.federated.experiment import run_experiment
from src.federated.optimizers import fedprox_gradient
from src.security.privacy import compose_gaussian_rdp


def test_multi_krum_rejects_invalid_byzantine_bound():
    with pytest.raises(ValueError, match="n > 2f"):
        multi_krum([np.array([float(i)]) for i in range(4)], byzantine_clients=1)


def test_multi_krum_reduces_single_extreme_outlier():
    updates = [np.array([1.0, 1.0]), np.array([1.1, 1.0]), np.array([0.9, 1.0]),
               np.array([1.0, 0.9]), np.array([100.0, -100.0])]
    result = multi_krum(updates, byzantine_clients=1, selected_clients=2)
    assert np.linalg.norm(result - np.array([1.0, 1.0])) < 0.2


def test_fedprox_gradient_is_zero_at_global_parameters():
    result = fedprox_gradient(np.array([1.0, 2.0]), np.array([3.0, 4.0]),
                              np.array([3.0, 4.0]), 0.5)
    np.testing.assert_allclose(result, [1.0, 2.0])


def test_fedprox_gradient_penalizes_local_drift():
    result = fedprox_gradient(np.zeros(2), np.array([2.0, 4.0]), np.array([1.0, 1.0]), 0.5)
    np.testing.assert_allclose(result, [0.5, 1.5])


def test_rdp_composition_accounts_for_multiple_rounds():
    one = compose_gaussian_rdp(noise_multiplier=2.0, rounds=1, delta=1e-5)
    many = compose_gaussian_rdp(noise_multiplier=2.0, rounds=10, delta=1e-5)
    assert many["composed_rounds_accounted"] is True
    assert many["epsilon"] > one["epsilon"]
    assert many["rounds"] == 10


def test_checkpoint_round_trip_and_metadata_validation(tmp_path):
    path = tmp_path / "federated.npz"
    params = np.array([1.0, 2.0, 3.0])
    save_checkpoint(path, round_number=7, global_parameters=params,
                    metadata={"dataset_hash": "abc", "algorithm": "fedprox"})
    loaded = load_checkpoint(path, expected_metadata={"dataset_hash": "abc"})
    assert loaded["round_number"] == 7
    np.testing.assert_allclose(loaded["global_parameters"], params)
    with pytest.raises(ValueError, match="metadata mismatch"):
        load_checkpoint(path, expected_metadata={"dataset_hash": "different"})


def test_fedprox_mode_is_exposed_in_experiment_config():
    result = run_experiment({"seed": 9, "clients": 4, "rounds": 2, "local_epochs": 1,
                             "samples": 300, "features": 8, "local_optimizer": "fedprox",
                             "fedprox_mu": 0.05})
    assert result["config"]["local_optimizer"] == "fedprox"
    assert result["config"]["fedprox_mu"] == pytest.approx(0.05)


def test_experiment_exposes_comparable_fedavg_fedprox_trimmed_mean_and_multi_krum():
    result = run_experiment({"seed": 27, "clients": 6, "rounds": 2, "local_epochs": 1,
                             "samples": 360, "features": 8, "attack": "none"})
    for method in ("fedavg", "fedprox", "trimmed_mean", "multi_krum", "trust", "hatta"):
        assert method in result["metrics"]
        assert 0.0 <= result["metrics"][method]["f1"] <= 1.0


def test_experiment_dp_baseline_reports_composed_client_level_accounting():
    result = run_experiment({"seed": 29, "clients": 6, "rounds": 2, "local_epochs": 1,
                             "samples": 360, "features": 8, "dp_enabled": True,
                             "dp_noise_multiplier": 2.0, "dp_clip_norm": 1.0})
    assert result["privacy"]["enabled"] is True
    assert result["privacy"]["composed_rounds_accounted"] is True
    assert result["privacy"]["rounds"] == 2
    assert "fedavg_dp" in result["metrics"]


def test_trust_update_uses_measured_contribution_utility():
    from src.federated.trust import update_trust

    poor_contribution = update_trust(0.5, 0.0, 1.0, 1.0, recovery=0.0)
    useful_contribution = update_trust(0.5, 1.0, 1.0, 1.0, recovery=0.0)
    assert useful_contribution > poor_contribution
    assert poor_contribution == pytest.approx(0.475)
    assert useful_contribution == pytest.approx(0.725)
