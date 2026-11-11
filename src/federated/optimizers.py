"""Local optimization helpers for federated-learning experiments."""
from __future__ import annotations

import numpy as np


def fedprox_gradient(
    gradient: np.ndarray,
    local_parameters: np.ndarray,
    global_parameters: np.ndarray,
    mu: float,
) -> np.ndarray:
    """Add the FedProx proximal gradient mu * (w_local - w_global)."""
    grad = np.asarray(gradient, dtype=float)
    local = np.asarray(local_parameters, dtype=float)
    global_ = np.asarray(global_parameters, dtype=float)
    if grad.shape != local.shape or local.shape != global_.shape:
        raise ValueError("gradient and parameter shapes must match")
    if not np.isfinite(grad).all() or not np.isfinite(local).all() or not np.isfinite(global_).all():
        raise ValueError("FedProx inputs must be finite")
    if not np.isfinite(mu) or mu < 0:
        raise ValueError("mu must be finite and non-negative")
    return grad + float(mu) * (local - global_)
