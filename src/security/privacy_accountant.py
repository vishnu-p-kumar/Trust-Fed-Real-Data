"""Conservative Gaussian-mechanism RDP accountant (full, non-subsampled bound)."""
from __future__ import annotations
import math
import numpy as np

class GaussianRDPAccountant:
    def __init__(self, orders=None):
        self.orders=np.asarray(orders if orders is not None else [1.25,1.5,2,3,4,5,8,10,16,20,32,64,128],dtype=float)
        if self.orders.ndim!=1 or len(self.orders)==0 or (self.orders<=1).any(): raise ValueError("RDP orders must be > 1")
        self.rdp=np.zeros_like(self.orders); self.steps=0
    def step(self, noise_multiplier: float, *, count: int=1):
        if not math.isfinite(noise_multiplier) or noise_multiplier<=0 or not isinstance(count,int) or count<1: raise ValueError("noise_multiplier and count must be positive")
        self.rdp += count*self.orders/(2*noise_multiplier**2); self.steps += count
    def epsilon(self, delta: float) -> float:
        if not 0<delta<1: raise ValueError("delta must be in (0,1)")
        return float(np.min(self.rdp + math.log(1/delta)/(self.orders-1)))
    def state_dict(self):
        return {"orders":self.orders.tolist(),"rdp":self.rdp.tolist(),"steps":self.steps,"accountant":"Gaussian RDP; no subsampling amplification"}
