import pytest
from src.federated.drift import PageHinkley


def test_page_hinkley_does_not_flag_stable_series():
    monitor = PageHinkley(delta=0.01, threshold=5.0, min_observations=10)
    for i in range(100):
        assert monitor.update(0.2 + (0.001 if i % 2 else -0.001)) is False


def test_page_hinkley_detects_upward_metric_shift():
    monitor = PageHinkley(delta=0.005, threshold=2.0, min_observations=10)
    for _ in range(30):
        monitor.update(0.1)
    results = [monitor.update(0.8) for _ in range(20)]
    assert any(results)
    assert monitor.state()["detected"] is True


def test_page_hinkley_rejects_nonfinite_observations():
    monitor = PageHinkley()
    with pytest.raises(ValueError):
        monitor.update(float("nan"))
