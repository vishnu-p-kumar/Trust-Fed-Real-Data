from __future__ import annotations

import numpy as np


def validation_harm(before_loss: float, after_loss: float) -> float:
    """Positive increase in held-out validation log loss caused by an update."""
    if not np.isfinite([before_loss, after_loss]).all():
        raise ValueError("validation losses must be finite")
    return float(max(0.0, after_loss - before_loss))


def robust_validation_threshold(harms: list[float], mad_multiplier: float = 2.5) -> float:
    """Set a round threshold from validation-only client harm observations.

    The median/MAD threshold tolerates a minority of harmful updates. It uses
    no client identity or attack labels. A small floor avoids treating tiny
    floating-point differences as evidence when all clients improve equally.
    """
    values = np.asarray(harms, dtype=float)
    if values.ndim != 1 or len(values) < 3 or not np.isfinite(values).all():
        raise ValueError("at least three finite validation harm values are required")
    if not np.isfinite(mad_multiplier) or mad_multiplier < 0:
        raise ValueError("mad_multiplier must be finite and non-negative")
    median = float(np.median(values))
    mad = float(np.median(np.abs(values - median)))
    return max(1e-6, median + mad_multiplier * 1.4826 * mad)


def select_detection_threshold(scores: list[float], malicious: list[bool], *,
                               max_false_accusation_rate: float = 0.10) -> float:
    """Choose a threshold on calibration runs, subject to a benign FPR limit.

    This is supervised simulation calibration: the controlled calibration
    scenarios provide attack labels. The selected threshold must be frozen
    before evaluation seeds are run.
    """
    values = np.asarray(scores, dtype=float)
    labels = np.asarray(malicious, dtype=bool)
    if (values.ndim != 1 or labels.ndim != 1 or len(values) != len(labels)
            or len(values) == 0 or not np.isfinite(values).all()):
        raise ValueError("scores and labels must be finite, non-empty, and aligned")
    if not 0 <= max_false_accusation_rate <= 1:
        raise ValueError("max_false_accusation_rate must be in [0, 1]")
    candidates = np.r_[np.inf, np.unique(values), -np.inf]
    best = (-1.0, -1.0)
    for threshold in candidates:
        flagged = values > threshold
        benign = ~labels
        fpr = float(flagged[benign].mean()) if benign.any() else 0.0
        tp = int((flagged & labels).sum())
        fp = int((flagged & benign).sum())
        precision = tp / max(1, tp + fp)
        recall = tp / max(1, int(labels.sum()))
        if fpr <= max_false_accusation_rate and (recall, precision) > best:
            best = (recall, precision)
            selected = float(threshold)
    return selected if best[0] >= 0 else float("inf")


def update_trust(previous: float, utility: float, integrity: float, temporal: float, *, recovery: float = 0.08) -> float:
    """Update a smoothed trust score from independently measured evidence.

    Inputs use [0, 1], where larger utility/integrity/temporal values are
    favorable. The score is descriptive; malicious-client decisions use a
    validation-calibrated harm threshold rather than an arbitrary trust floor.
    """
    values=np.asarray([previous,utility,integrity,temporal,recovery],dtype=float)
    if not np.isfinite(values).all() or recovery < 0:
        raise ValueError("trust evidence and recovery must be finite; recovery must be non-negative")
    prev=float(np.clip(previous,0,1))
    vals = np.clip([utility, integrity, temporal], 0.0, 1.0)
    score = 0.55 * prev + 0.25 * vals[0] + 0.12 * vals[1] + 0.08 * vals[2]
    return float(np.clip(score + recovery * max(0.0, 0.5 - prev), 0.0, 1.0))


def normalized_weights(trust: list[float], sizes: list[int]) -> np.ndarray:
    scores = np.asarray(trust, dtype=float)
    sample_sizes = np.asarray(sizes, dtype=float)
    if (scores.ndim != 1 or sample_sizes.ndim != 1 or len(scores) == 0 or len(scores) != len(sample_sizes)
            or not np.isfinite(scores).all() or not np.isfinite(sample_sizes).all() or (sample_sizes <= 0).any()):
        raise ValueError("trust scores and positive client sizes must be finite and aligned")
    normalized_sizes=sample_sizes/sample_sizes.max()
    values = np.clip(scores, 0.0, 1.0) * normalized_sizes
    if values.sum() <= 0: return normalized_sizes / normalized_sizes.sum()
    return values / values.sum()
