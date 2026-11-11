"""Pairwise-mask secure-sum reference implementation with replay protection.

This module is deliberately labelled a research/reference protocol. It assumes
pairwise keys have already been provisioned securely and all participants finish
the round. It does not implement dropout recovery, malicious-client robustness,
key agreement, distributed key erasure or a formally audited protocol; do not
advertise it as production secure aggregation.
"""
from __future__ import annotations
import hashlib
import hmac
import math
import threading
import numpy as np


def _uniform_stream(secret: bytes, context: bytes, count: int) -> np.ndarray:
    """HMAC-SHA256 counter-mode pseudorandom stream mapped to open-interval uniforms."""
    blocks=[]; counter=0
    while sum(len(x) for x in blocks) < count * 8:
        blocks.append(hmac.new(secret, context + counter.to_bytes(8,"big"), hashlib.sha256).digest())
        counter += 1
    raw=b"".join(blocks)[:count*8]
    integers=np.frombuffer(raw,dtype=">u8").astype(np.float64)
    return (integers + 0.5) / (2.0**64)


def _pairwise_mask(secret: bytes, round_id: str, a: str, b: str, shape: tuple[int,...]) -> np.ndarray:
    if not isinstance(secret,bytes) or len(secret)<32:
        raise ValueError("pairwise keys must contain at least 256 bits")
    context="|".join(("trustfed-secagg-v2",round_id,*sorted((a,b)),repr(shape))).encode()
    count=int(np.prod(shape)); u1=_uniform_stream(secret,context+b"|u1",count)
    u2=_uniform_stream(secret,context+b"|u2",count)
    z=np.sqrt(-2.0*np.log(u1))*np.cos(2.0*math.pi*u2)
    return z.reshape(shape)


class SecureAggregationSession:
    """One-shot all-participant secure-sum session with pairwise mask cancellation."""
    def __init__(self, pairwise_keys: dict[tuple[str,str],bytes]):
        self._keys=dict(pairwise_keys); self._used_rounds:set[str]=set(); self._lock=threading.Lock()

    def aggregate(self, updates: dict[str,np.ndarray], *, round_id: str) -> dict[str,object]:
        if not round_id or len(round_id)>128: raise ValueError("round_id is required and must be <=128 chars")
        names=sorted(updates)
        if len(names)<2 or len(names)!=len(set(names)): raise ValueError("at least two uniquely named clients are required")
        arrays={name:np.asarray(updates[name],dtype=np.float64) for name in names}
        shape=arrays[names[0]].shape
        if any(a.size==0 or a.shape!=shape or not np.isfinite(a).all() for a in arrays.values()):
            raise ValueError("all updates must be non-empty, finite and identically shaped")
        # Reserve the nonce before processing; failed rounds cannot be replayed.
        with self._lock:
            if round_id in self._used_rounds: raise ValueError("round_id replay rejected")
            self._used_rounds.add(round_id)
        masked={name:a.copy() for name,a in arrays.items()}
        commitments=[]
        for i,left in enumerate(names):
            for right in names[i+1:]:
                key=self._keys.get((left,right)) or self._keys.get((right,left))
                if not isinstance(key,bytes) or len(key)<32:
                    raise ValueError(f"missing 256-bit pairwise key for {left}/{right}")
                context=f"{round_id}|{left}|{right}".encode()
                commitments.append(hmac.new(key,context,hashlib.sha256).hexdigest())
                mask=_pairwise_mask(key,round_id,left,right,shape)
                masked[left]+=mask; masked[right]-=mask
        total=np.sum(np.stack([masked[name] for name in names]),axis=0)
        return {"aggregate":total,"round_id":round_id,"participants":len(names),
                "pairwise_commitments":commitments,"protocol":"pairwise HMAC-PRF mask cancellation v2",
                "security_status":"research_reference_only_no_dropout_recovery_or_audit"}


def masked_sum(updates: dict[str,np.ndarray], *, secret: bytes, round_id: str) -> np.ndarray:
    """Backward-compatible single-root-secret demonstration; not production use."""
    if len(updates)<2 or not secret: raise ValueError("at least two clients and a shared secret are required")
    names=sorted(updates); keys={(a,b):hmac.new(secret,f"{round_id}|{a}|{b}".encode(),hashlib.sha256).digest() for i,a in enumerate(names) for b in names[i+1:]}
    return SecureAggregationSession(keys).aggregate(updates,round_id=round_id)["aggregate"]
