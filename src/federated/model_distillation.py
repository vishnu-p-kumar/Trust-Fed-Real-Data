"""Federated model-family bridge using prediction distillation on a shared anchor set.

Tree ensembles, anomaly detectors and forecasters do not share parameter spaces;
averaging their serialized parameters is mathematically invalid. This module combines
their outputs on a governed anchor matrix and fits a compact student classifier.
Anchor rows must be non-sensitive, licensed and schema-compatible.
"""
from __future__ import annotations
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss

def _positive_probability(model, X):
    if hasattr(model,"predict_proba"):
        p=np.asarray(model.predict_proba(X),dtype=float)
        if p.ndim==2:
            classes=list(getattr(model,"classes_",range(p.shape[1])))
            return p[:,classes.index(1)] if 1 in classes else p[:,-1]
        return p.reshape(-1)
    if hasattr(model,"decision_function"):
        z=np.asarray(model.decision_function(X),dtype=float).reshape(-1)
        return 1/(1+np.exp(-np.clip(z,-30,30)))
    raise TypeError("model must implement predict_proba or decision_function")

def federated_teacher_targets(client_models, anchor_X, *, client_weights=None, clip=(1e-5,1-1e-5)):
    X=np.asarray(anchor_X,dtype=float)
    if X.ndim!=2 or len(X)==0 or not np.isfinite(X).all() or not client_models:
        raise ValueError("anchor_X and client_models must be non-empty and finite")
    probs=np.stack([np.clip(_positive_probability(m,X),*clip) for m in client_models])
    if client_weights is None: weights=np.ones(len(client_models),dtype=float)
    else: weights=np.asarray(client_weights,dtype=float)
    if weights.shape!=(len(client_models),) or not np.isfinite(weights).all() or (weights<0).any() or weights.sum()<=0:
        raise ValueError("invalid client weights")
    weights=weights/weights.sum()
    return np.average(probs,axis=0,weights=weights),probs

def distill_global_student(anchor_X, teacher_probabilities, *, C=1.0, seed=42):
    X=np.asarray(anchor_X,dtype=float); p=np.asarray(teacher_probabilities,dtype=float)
    if X.ndim!=2 or p.shape!=(len(X),) or len(X)<2 or not np.isfinite(X).all() or not np.isfinite(p).all() or ((p<0)|(p>1)).any():
        raise ValueError("invalid anchor features or teacher probabilities")
    # Soft targets are converted to weighted binary pseudo-labels; retain the
    # confidence as sample weight to reduce influence of uncertain teacher outputs.
    labels=(p>=.5).astype(int); confidence=np.maximum(p,1-p)
    if len(np.unique(labels))<2: raise ValueError("teacher targets must contain both classes")
    student=LogisticRegression(C=C,random_state=seed,max_iter=1000)
    student.fit(X,labels,sample_weight=confidence)
    predicted=student.predict_proba(X)[:,1]
    return student,{"anchor_rows":int(len(X)),"teacher_student_log_loss":float(log_loss(labels,predicted)),
                    "mean_teacher_confidence":float(confidence.mean()),
                    "warning":"Distillation quality depends on anchor-set representativeness; not equivalent to parameter-level federated training."}
