"""Data and model drift monitoring utilities."""
from __future__ import annotations
import numpy as np

def population_stability_index(reference, current, bins=10, epsilon=1e-6):
    ref=np.asarray(reference,dtype=float); cur=np.asarray(current,dtype=float)
    if ref.ndim!=1 or cur.ndim!=1 or len(ref)==0 or len(cur)==0 or not np.isfinite(ref).all() or not np.isfinite(cur).all():
        raise ValueError("reference/current must be non-empty finite vectors")
    if bins<2 or epsilon<=0: raise ValueError("bins must be >=2 and epsilon positive")
    edges=np.unique(np.quantile(ref,np.linspace(0,1,bins+1)))
    if len(edges)<3: return 0.0
    edges[0],edges[-1]=-np.inf,np.inf
    a=np.histogram(ref,bins=edges)[0].astype(float); b=np.histogram(cur,bins=edges)[0].astype(float)
    p=np.clip(a/a.sum(),epsilon,None); q=np.clip(b/b.sum(),epsilon,None)
    p/=p.sum(); q/=q.sum()
    return float(np.sum((q-p)*np.log(q/p)))

def binary_calibration_error(probabilities, labels, bins=10):
    p=np.asarray(probabilities,dtype=float); y=np.asarray(labels,dtype=int)
    if p.ndim!=1 or y.shape!=p.shape or len(p)==0 or not np.isfinite(p).all() or ((p<0)|(p>1)).any() or not np.isin(y,[0,1]).all():
        raise ValueError("invalid probabilities or binary labels")
    edges=np.linspace(0,1,bins+1); error=0.0
    for i in range(bins):
        mask=(p>=edges[i]) & ((p<edges[i+1]) if i<bins-1 else (p<=edges[i+1]))
        if mask.any(): error += mask.mean()*abs(p[mask].mean()-y[mask].mean())
    return float(error)
