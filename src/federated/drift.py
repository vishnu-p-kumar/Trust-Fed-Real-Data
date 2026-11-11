"""Lightweight online Page-Hinkley drift monitor for meter/model metrics."""
from __future__ import annotations
from dataclasses import dataclass
import math

@dataclass
class PageHinkley:
    delta: float = 0.005
    threshold: float = 5.0
    alpha: float = 0.99
    min_observations: int = 20

    def __post_init__(self):
        if not math.isfinite(self.delta) or self.delta < 0:
            raise ValueError("delta must be finite and non-negative")
        if not math.isfinite(self.threshold) or self.threshold <= 0:
            raise ValueError("threshold must be positive and finite")
        if not 0 < self.alpha <= 1:
            raise ValueError("alpha must be in (0, 1]")
        if self.min_observations < 2:
            raise ValueError("min_observations must be >= 2")
        self.reset()

    def reset(self):
        self.count = 0
        self.mean = 0.0
        self.cumulative = 0.0
        self.minimum = 0.0
        self.detected = False

    def update(self, value: float) -> bool:
        """Return True when an upward shift in the monitored metric is detected."""
        if not math.isfinite(float(value)):
            raise ValueError("drift observation must be finite")
        self.count += 1
        x = float(value)
        self.mean += (x - self.mean) / self.count
        self.cumulative = self.alpha * self.cumulative + (x - self.mean - self.delta)
        self.minimum = min(self.minimum, self.cumulative)
        if self.count >= self.min_observations and self.cumulative - self.minimum > self.threshold:
            self.detected = True
        return self.detected

    def state(self) -> dict:
        return {"count": self.count, "mean": self.mean, "cumulative": self.cumulative,
                "detected": self.detected, "delta": self.delta,
                "threshold": self.threshold, "alpha": self.alpha}
