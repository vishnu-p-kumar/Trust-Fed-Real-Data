"""Atomic checkpoint persistence for resumable federated experiments."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np


def save_checkpoint(path: str | Path, *, round_number: int, global_parameters: np.ndarray,
                    metadata: dict[str, Any] | None = None) -> Path:
    if not isinstance(round_number, int) or round_number < 0:
        raise ValueError("round_number must be a non-negative integer")
    params = np.asarray(global_parameters, dtype=float)
    if params.size == 0 or not np.isfinite(params).all():
        raise ValueError("global_parameters must be non-empty and finite")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"round_number": round_number, "metadata": metadata or {}}
    # Store numeric arrays in NPZ and metadata as JSON; never load pickled objects.
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".npz", delete=False) as tmp:
        temp_path = Path(tmp.name)
    try:
        np.savez_compressed(temp_path, global_parameters=params,
                            state_json=np.asarray(json.dumps(payload, sort_keys=True)))
        os.replace(temp_path, target)
    finally:
        if temp_path.exists():
            temp_path.unlink()
    return target


def load_checkpoint(path: str | Path, *, expected_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    target = Path(path)
    if not target.is_file():
        raise FileNotFoundError(target)
    with np.load(target, allow_pickle=False) as archive:
        params = np.asarray(archive["global_parameters"], dtype=float)
        state = json.loads(str(archive["state_json"].item()))
    if params.size == 0 or not np.isfinite(params).all():
        raise ValueError("checkpoint parameters are invalid")
    metadata = state.get("metadata", {})
    if expected_metadata is not None:
        mismatches = {key: (metadata.get(key), value) for key, value in expected_metadata.items()
                      if metadata.get(key) != value}
        if mismatches:
            raise ValueError(f"checkpoint metadata mismatch: {mismatches}")
    return {"round_number": int(state["round_number"]), "global_parameters": params,
            "metadata": metadata}
