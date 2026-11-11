from __future__ import annotations

import numpy as np


def flip_labels(y: np.ndarray, fraction: float = 1.0, seed: int = 42) -> np.ndarray:
    if not 0 <= fraction <= 1:
        raise ValueError("fraction must be in [0,1]")
    result = np.asarray(y, dtype=int).copy()
    ids = np.flatnonzero(np.random.default_rng(seed).random(len(result)) < fraction)
    result[ids] = 1 - result[ids]
    return result


def manipulate_update(update: np.ndarray, mode: str, intensity: float = 5.0) -> np.ndarray:
    """Apply a simple untargeted update attack before coordinator clipping."""
    values = np.asarray(update, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not np.isfinite(intensity) or intensity <= 0:
        raise ValueError("update must be non-empty and finite; intensity must be positive")
    if mode == "scale":
        return values * intensity
    if mode == "sign":
        return -values * intensity
    if mode == "slow":
        return -values * min(intensity, 1.25)
    raise ValueError("attack mode must be scale, sign, or slow")


def poison_backdoor(x: np.ndarray, y: np.ndarray, *, fraction: float = 0.2,
                    trigger_value: float = 5.0, target_label: int = 1,
                    seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Inject a synthetic feature trigger and target label into selected local rows."""
    features = np.asarray(x, dtype=float).copy()
    labels = np.asarray(y, dtype=int).copy()
    if features.ndim != 2 or labels.ndim != 1 or len(features) != len(labels) or features.shape[1] == 0:
        raise ValueError("x must be 2D, y must be 1D, and row counts must match")
    if not np.isfinite(features).all() or not np.isfinite(trigger_value):
        raise ValueError("features and trigger_value must be finite")
    if not 0 <= fraction <= 1 or target_label not in (0, 1):
        raise ValueError("fraction must be in [0,1] and target_label must be binary")
    ids = np.flatnonzero(np.random.default_rng(seed).random(len(labels)) < fraction)
    features[ids, 0] = trigger_value
    labels[ids] = target_label
    return features, labels


def add_gaussian_update_noise(update: np.ndarray, *, std: float, seed: int = 42) -> np.ndarray:
    values = np.asarray(update, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not np.isfinite(std) or std <= 0:
        raise ValueError("update must be non-empty and finite; std must be positive")
    return values + np.random.default_rng(seed).normal(0.0, std, size=values.shape)


def collude_update(update: np.ndarray, shared_direction: np.ndarray, strength: float = 1.0) -> np.ndarray:
    """Add the same coordinated perturbation direction to colluding clients."""
    values = np.asarray(update, dtype=float)
    direction = np.asarray(shared_direction, dtype=float)
    if values.shape != direction.shape or values.size == 0 or not np.isfinite(values).all() or not np.isfinite(direction).all():
        raise ValueError("update and shared direction must be finite, non-empty, and shape-aligned")
    if not np.isfinite(strength) or strength <= 0:
        raise ValueError("strength must be positive and finite")
    norm = float(np.linalg.norm(direction))
    if norm <= 0:
        raise ValueError("shared direction must have non-zero norm")
    return values + strength * direction / norm


def model_replacement_update(update: np.ndarray, *, scale: float) -> np.ndarray:
    """Scale a local delta to simulate a model-replacement attempt; coordinator clipping still applies."""
    values = np.asarray(update, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not np.isfinite(scale) or scale <= 0:
        raise ValueError("update must be non-empty and finite; scale must be positive")
    return values * scale



def low_slow_update(update: np.ndarray, *, severity: float, seed: int = 42) -> np.ndarray:
    """Low-amplitude coordinated poisoning intended to evade norm-only detectors.

    The perturbation is bounded relative to the submitted update norm. It is a
    controlled simulation, not a model of every adaptive adversary.
    """
    values = np.asarray(update, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not 0 < severity <= 1:
        raise ValueError("update must be finite/non-empty and severity must be in (0, 1]")
    rng = np.random.default_rng(seed)
    direction = rng.normal(size=values.shape)
    direction /= max(float(np.linalg.norm(direction)), 1e-12)
    base_norm = max(float(np.linalg.norm(values)), 1e-8)
    # A small opposing perturbation is intentionally difficult to detect by norm alone.
    return values - direction * (severity * base_norm)


def adaptive_mimic_update(update: np.ndarray, previous_update: np.ndarray | None, *,
                          mimic_strength: float = 0.7, seed: int = 42) -> np.ndarray:
    """Blend a current update with a prior benign-looking direction.

    This simulates an attacker trying to preserve temporal similarity while
    gradually perturbing the update. The previous update is not treated as
    trustworthy ground truth.
    """
    values = np.asarray(update, dtype=float)
    if values.size == 0 or not np.isfinite(values).all() or not 0 <= mimic_strength < 1:
        raise ValueError("invalid update or mimic_strength")
    if previous_update is None:
        return values.copy()
    previous = np.asarray(previous_update, dtype=float)
    if previous.shape != values.shape or not np.isfinite(previous).all():
        raise ValueError("previous update must be finite and shape-aligned")
    rng = np.random.default_rng(seed)
    # Add a small deterministic seeded orthogonal-ish perturbation to avoid exact replay.
    perturbation = rng.normal(size=values.shape)
    perturbation /= max(float(np.linalg.norm(perturbation)), 1e-12)
    scale = max(float(np.linalg.norm(values)), 1e-8) * 0.05
    return (1.0 - mimic_strength) * values + mimic_strength * previous + scale * perturbation
