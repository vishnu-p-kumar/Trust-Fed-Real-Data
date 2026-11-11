import numpy as np
import pytest

from src.federated.attacks import (
    add_gaussian_update_noise, collude_update, model_replacement_update,
    poison_backdoor, low_slow_update, adaptive_mimic_update,
)
from src.federated.experiment import run_experiment


def test_backdoor_poisoning_is_deterministic_and_targets_selected_rows():
    x = np.zeros((100, 3))
    y = np.zeros(100, dtype=int)
    x2, y2 = poison_backdoor(x, y, fraction=0.3, trigger_value=7.0, seed=19)
    x3, y3 = poison_backdoor(x, y, fraction=0.3, trigger_value=7.0, seed=19)
    np.testing.assert_array_equal(x2, x3)
    np.testing.assert_array_equal(y2, y3)
    changed = x2[:, 0] == 7.0
    assert 15 <= changed.sum() <= 45
    assert np.all(y2[changed] == 1)
    assert np.all(x[:, 0] == 0)


def test_gaussian_attack_is_seeded_and_changes_update():
    update = np.zeros(5)
    first = add_gaussian_update_noise(update, std=0.5, seed=3)
    second = add_gaussian_update_noise(update, std=0.5, seed=3)
    np.testing.assert_array_equal(first, second)
    assert np.any(first != 0)


def test_collusion_uses_same_shared_direction():
    direction = np.array([3.0, 4.0])
    first = collude_update(np.zeros(2), direction, strength=2.0)
    second = collude_update(np.ones(2), direction, strength=2.0)
    np.testing.assert_allclose(second - first, np.ones(2))
    assert np.linalg.norm(first) == pytest.approx(2.0)


def test_model_replacement_scales_update():
    np.testing.assert_allclose(model_replacement_update(np.array([1., -2.]), scale=4), [4., -8.])


@pytest.mark.parametrize("attack", ["backdoor", "gaussian", "collusion", "model_replacement", "stale"])
def test_new_attack_modes_run_end_to_end(attack):
    result = run_experiment({
        "seed": 13, "clients": 6, "rounds": 2, "local_epochs": 1,
        "samples": 360, "features": 8, "partition": "severe",
        "attack": attack, "malicious_fraction": 0.34,
        "attack_intensity": 1.5, "max_update_norm": 5.0,
    })
    assert result["config"]["attack"] == attack
    assert len(result["rounds"]) == 2
    assert result["security"]["attack_success_rate"] is None if attack != "backdoor" else (
        0.0 <= result["security"]["attack_success_rate"] <= 1.0
    )



def test_low_slow_attack_is_bounded_and_deterministic():
    update = np.array([0.2, -0.1, 0.05])
    first = low_slow_update(update, severity=0.2, seed=31)
    second = low_slow_update(update, severity=0.2, seed=31)
    np.testing.assert_array_equal(first, second)
    assert np.linalg.norm(first - update) == pytest.approx(0.2 * np.linalg.norm(update))


def test_adaptive_mimic_attack_preserves_previous_direction_component():
    current = np.array([1.0, 0.0, 0.0])
    previous = np.array([0.0, 1.0, 0.0])
    result = adaptive_mimic_update(current, previous, mimic_strength=0.8, seed=7)
    assert result[1] > result[0]
    assert np.isfinite(result).all()


@pytest.mark.parametrize("attack", ["low_slow", "adaptive_mimic"])
def test_adaptive_attack_modes_run_end_to_end(attack):
    result = run_experiment({
        "seed": 21, "clients": 6, "rounds": 3, "local_epochs": 1,
        "samples": 360, "features": 8, "partition": "severe",
        "attack": attack, "malicious_fraction": 0.34,
        "attack_intensity": 1.5, "max_update_norm": 5.0,
        "trust_bad_round_patience": 2,
    })
    assert result["config"]["attack"] == attack
    assert len(result["rounds"]) == 3
    assert result["security"]["attack"] is not None


def test_dp_trust_evidence_is_explicitly_scoped():
    result = run_experiment({
        "seed": 22, "clients": 6, "rounds": 2, "local_epochs": 1,
        "samples": 360, "features": 8, "partition": "severe",
        "trust_dp_enabled": True, "trust_dp_noise_multiplier": 2.0,
    })
    assert result["trust_privacy"]["enabled"] is True
    assert result["trust_privacy"]["epsilon"] > 0
    assert "does not make HATTA end-to-end" in result["trust_privacy"]["limitations"]


def test_research_api_schema_accepts_all_implemented_adaptive_attacks():
    from api.main import ResearchExperimentRequest

    for attack in ("low_slow", "adaptive_mimic"):
        payload = ResearchExperimentRequest.model_validate({"attack": attack})
        assert payload.attack == attack
