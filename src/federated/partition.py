from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ClientPartition:
    client_id: str
    indices: np.ndarray


def stratified_group_holdout(y: np.ndarray, groups: np.ndarray, test_size: float = .2,
                             seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Return row indices for a customer-disjoint split, stratified by any-positive group label."""
    labels = np.asarray(y, dtype=int)
    group_values = np.asarray(groups).astype(str)
    if labels.ndim != 1 or group_values.ndim != 1 or len(labels) != len(group_values):
        raise ValueError("labels and groups must be aligned one-dimensional arrays")
    unique, inverse = np.unique(group_values, return_inverse=True)
    if len(unique) < 5:
        raise ValueError("customer-disjoint evaluation requires at least five groups")
    if not 0 < test_size < 1:
        raise ValueError("test_size must be in (0,1)")
    group_labels = np.asarray([int(labels[inverse == idx].max()) for idx in range(len(unique))])
    positive_groups = np.flatnonzero(group_labels == 1)
    negative_groups = np.flatnonzero(group_labels == 0)
    if min(len(positive_groups), len(negative_groups)) < 2:
        raise ValueError("customer-disjoint evaluation requires at least two meter groups in each target class")
    test_count = min(len(unique) - 2, max(2, int(np.ceil(len(unique) * test_size))))
    test_positive_count = min(len(positive_groups) - 1,
                              max(1, int(round(test_count * len(positive_groups) / len(unique)))))
    test_negative_count = test_count - test_positive_count
    if test_negative_count > len(negative_groups) - 1:
        test_negative_count = len(negative_groups) - 1
        test_positive_count = test_count - test_negative_count
    rng = np.random.default_rng(seed)
    test_groups = np.concatenate([
        rng.choice(positive_groups, size=test_positive_count, replace=False),
        rng.choice(negative_groups, size=test_negative_count, replace=False),
    ])
    train_groups = np.setdiff1d(np.arange(len(unique)), test_groups, assume_unique=False)
    train_mask = np.isin(inverse, train_groups)
    test_mask = np.isin(inverse, test_groups)
    return np.flatnonzero(train_mask), np.flatnonzero(test_mask)


def partition_clients(y: np.ndarray, clients: int = 8, mode: str = "moderate", seed: int = 42) -> list[ClientPartition]:
    """Partition row indices using deterministic label allocation, never sharing records."""
    labels = np.asarray(y, dtype=int)
    if clients < 2 or len(labels) < clients:
        raise ValueError("clients must be >= 2 and no larger than the sample count")
    if mode not in {"iid", "moderate", "severe"}:
        raise ValueError("mode must be iid, moderate, or severe")
    rng = np.random.default_rng(seed)
    bins: list[list[int]] = [[] for _ in range(clients)]
    for label in np.unique(labels):
        ids = np.flatnonzero(labels == label)
        rng.shuffle(ids)
        if mode == "iid":
            chunks = np.array_split(ids, clients)
            for k, chunk in enumerate(chunks): bins[k].extend(chunk.tolist())
        else:
            alpha = 0.7 if mode == "moderate" else 0.12
            proportions = rng.dirichlet(np.full(clients, alpha))
            cuts = (np.cumsum(proportions)[:-1] * len(ids)).astype(int)
            for k, chunk in enumerate(np.split(ids, cuts)): bins[k].extend(chunk.tolist())
    # Empty bins are possible under severe skew; rebalance by moving one record from the largest.
    for k, group in enumerate(bins):
        if not group:
            donor = max(range(clients), key=lambda i: len(bins[i]))
            group.append(bins[donor].pop())
    return [ClientPartition(f"client_{k:03d}", np.asarray(sorted(v), dtype=int)) for k, v in enumerate(bins)]


def partition_by_group(groups: np.ndarray, clients: int, seed: int = 42) -> list[ClientPartition]:
    """Assign complete meter/customer groups to disjoint federated clients.

    Each unique group is assigned once; all its row indices stay on the same
    client. This is appropriate for unlabeled meter datasets where label-based
    client allocation is unavailable or scientifically inappropriate.
    """
    values = np.asarray(groups)
    if values.ndim != 1 or values.size == 0 or clients < 2:
        raise ValueError("groups must be a non-empty vector and clients must be >= 2")
    if _missing_group_mask(values).any():
        raise ValueError("group identifiers must not be missing")
    unique = np.unique(values.astype(str))
    if len(unique) < clients:
        raise ValueError("client count cannot exceed the number of unique groups")
    rng = np.random.default_rng(seed)
    rng.shuffle(unique)
    allocations = np.array_split(unique, clients)
    result = []
    for index, client_groups in enumerate(allocations):
        row_indices = np.flatnonzero(np.isin(values.astype(str), client_groups))
        result.append(ClientPartition(f"client_{index:03d}", row_indices))
    return result


def _missing_group_mask(values: np.ndarray) -> np.ndarray:
    return np.asarray([value is None or str(value).strip().lower() in {"", "nan", "none", "<na>"}
                       or (isinstance(value, float) and np.isnan(value)) for value in values])
