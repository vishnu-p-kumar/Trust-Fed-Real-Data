from __future__ import annotations

import numpy as np
import pandas as pd

from src.theft_detector import _calibrate_theft_probability


def test_theft_probability_does_not_use_synthetic_seed_or_anomaly_metadata() -> None:
    frame = pd.DataFrame(
        [
            {
                "seeded_theft_probability": 0.94,
                "anomaly_score": 0.62,
                "wastage_score": 0.28,
            },
            {
                "seeded_theft_probability": 0.08,
                "anomaly_score": 0.12,
                "wastage_score": 0.05,
            },
        ]
    )

    calibrated = _calibrate_theft_probability(
        frame,
        rf_probability=np.array([0.84, 0.18]),
        boost_probability=np.array([0.92, 0.22]),
    )

    assert np.allclose(calibrated, [0.884, 0.202])


def test_generator_metadata_cannot_change_theft_probability() -> None:
    plain = pd.DataFrame({"seeded_theft_probability": [0.0], "is_theft": [0]})
    seeded = pd.DataFrame({"seeded_theft_probability": [0.99], "is_theft": [1]})
    p = np.array([0.2])
    b = np.array([0.4])
    assert np.array_equal(_calibrate_theft_probability(plain, p, b), _calibrate_theft_probability(seeded, p, b))
