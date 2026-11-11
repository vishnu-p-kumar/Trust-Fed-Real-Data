"""SCAFFOLD control-variate optimizer primitives for federated training."""
from __future__ import annotations
import numpy as np

def scaffold_gradient(gradient, local_control, server_control):
    g=np.asarray(gradient,dtype=float); ci=np.asarray(local_control,dtype=float); c=np.asarray(server_control,dtype=float)
    if g.shape != ci.shape or ci.shape != c.shape: raise ValueError("SCAFFOLD vectors must have matching shapes")
    if not all(np.isfinite(x).all() for x in (g,ci,c)): raise ValueError("SCAFFOLD vectors must be finite")
    return g-ci+c

def update_client_control(old_control, global_parameters, local_parameters, learning_rate, local_steps):
    old=np.asarray(old_control,dtype=float); glob=np.asarray(global_parameters,dtype=float); local=np.asarray(local_parameters,dtype=float)
    if old.shape != glob.shape or glob.shape != local.shape: raise ValueError("control and parameter shapes must match")
    if not np.isfinite([learning_rate,local_steps]).all() or learning_rate<=0 or local_steps<=0: raise ValueError("learning_rate and local_steps must be positive")
    if not all(np.isfinite(x).all() for x in (old,glob,local)): raise ValueError("inputs must be finite")
    return old - glob/(learning_rate*local_steps) + local/(learning_rate*local_steps)
