from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.datasets import make_classification
from sklearn.metrics import (accuracy_score, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, average_precision_score)
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer

from src.federated.aggregators import fedavg, trimmed_mean, trust_weighted, multi_krum
from src.security.privacy import gaussian_dp_aggregate, compose_gaussian_rdp
from src.federated.optimizers import fedprox_gradient
from src.federated.attacks import (flip_labels, manipulate_update, poison_backdoor,
                                   add_gaussian_update_noise, collude_update,
                                   model_replacement_update, low_slow_update, adaptive_mimic_update)
from src.federated.partition import partition_clients, stratified_group_holdout
from src.federated.trust import (normalized_weights, robust_validation_threshold, select_detection_threshold,
                                 update_trust, validation_harm)


def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(z, -35, 35)))


def _clip_update(update: np.ndarray, max_norm: float) -> tuple[np.ndarray | None, float]:
    values = np.asarray(update, dtype=float)
    if max_norm <= 0 or not np.isfinite(values).all():
        return None, float("inf")
    norm = float(np.linalg.norm(values))
    if not np.isfinite(norm):
        return None, norm
    scale = min(1.0, max_norm / max(norm, 1e-12))
    return values * scale, norm


def _fit(x: np.ndarray, y: np.ndarray, initial: np.ndarray, epochs: int, lr: float, batch_size: int, seed: int, *, prox_mu: float = 0.0, global_parameters: np.ndarray | None = None) -> np.ndarray:
    w = initial.copy()
    reference = initial.copy() if global_parameters is None else np.asarray(global_parameters, dtype=float).copy()
    if reference.shape != w.shape or not np.isfinite(reference).all() or prox_mu < 0 or not np.isfinite(prox_mu):
        raise ValueError("invalid FedProx reference parameters or coefficient")
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        order = rng.permutation(len(y))
        for start in range(0, len(y), batch_size):
            idx = order[start:start+batch_size]
            xb, yb = x[idx], y[idx]
            p = _sigmoid(xb @ w[:-1] + w[-1])
            grad = np.r_[xb.T @ (p-yb) / max(1, len(yb)) + 1e-4*w[:-1], np.mean(p-yb)]
            if prox_mu:
                grad = fedprox_gradient(grad, w, reference, prox_mu)
            w -= lr * grad
    return w


def _metrics(w: np.ndarray, x: np.ndarray, y: np.ndarray) -> dict[str, Any]:
    p = _sigmoid(x @ w[:-1] + w[-1]); pred = (p >= .5).astype(int)
    cm = confusion_matrix(y, pred, labels=[0,1]); tn, fp, fn, tp = cm.ravel()
    return {"accuracy": float(accuracy_score(y,pred)), "precision": float(precision_score(y,pred,zero_division=0)),
            "recall": float(recall_score(y,pred,zero_division=0)), "f1": float(f1_score(y,pred,zero_division=0)),
            "macro_f1": float(f1_score(y,pred,average="macro",zero_division=0)),
            "pr_auc": float(average_precision_score(y,p)) if len(np.unique(y))>1 else 0.0,
            "roc_auc": float(roc_auc_score(y,p)) if len(np.unique(y))>1 else 0.5,
            "false_positive_rate": float(fp/max(1,fp+tn)), "confusion_matrix": cm.tolist(),
            "n": int(len(y)), "prediction_mean": float(p.mean())}


def _binary_log_loss(w: np.ndarray, x: np.ndarray, y: np.ndarray) -> float:
    probability = np.clip(_sigmoid(x @ w[:-1] + w[-1]), 1e-7, 1 - 1e-7)
    return float(-np.mean(y * np.log(probability) + (1 - y) * np.log(1 - probability)))


def _summary_stats(values: list[float], bounds: tuple[float,float] | None = (0.0,1.0)) -> dict[str, Any]:
    array=np.asarray(values,dtype=float)
    if array.size == 0 or not np.isfinite(array).all():
        raise ValueError("summary values must be non-empty and finite")
    mean=float(array.mean())
    if array.size < 2:
        return {"mean":mean,"std":0.0,"ci95":[None,None],"n":int(array.size)}
    critical={2:12.706,3:4.303,4:3.182,5:2.776,6:2.571,7:2.447,8:2.365,9:2.306,10:2.262,
              11:2.228,12:2.201,13:2.179,14:2.160,15:2.145,16:2.131,17:2.120,18:2.110,
              19:2.101,20:2.093,21:2.086,22:2.080,23:2.074,24:2.069,25:2.064,26:2.060,
              27:2.056,28:2.052,29:2.048,30:2.045}
    std=float(array.std(ddof=1))
    q=critical.get(int(array.size),1.96)
    half=q*std/math.sqrt(array.size)
    interval=[mean-half,mean+half]
    if bounds is not None:
        interval=[max(bounds[0],interval[0]),min(bounds[1],interval[1])]
    return {"mean":mean,"std":std,"ci95":interval,"n":int(array.size)}


def run_experiment(config: dict[str, Any] | None = None, *, output_dir: str | Path | None = None,
                   dataframe: pd.DataFrame | None = None) -> dict[str, Any]:
    """Small CPU experiment. Client records remain local to each loop iteration."""
    cfg = {"seed":42,"clients":8,"rounds":8,"local_epochs":3,"batch_size":64,"learning_rate":.12,
           "partition":"moderate","attack":"none","malicious_fraction":.25,"attack_intensity":4.0,
           "label_flip_fraction":1.0,"benign_shift_strength":0.0,"trust_evidence":"utility_integrity",
           "detection_threshold":None,"trust_mad_multiplier":2.5,"max_false_accusation_rate":.10,
           "trust_recovery_rate":.08,"heterogeneity_weight":.5,"trust_bad_round_patience":2,
            "trust_dp_enabled":False,"trust_dp_noise_multiplier":2.0,
           "attack_start_round":1,"attack_end_round":None,
           "max_update_norm":5.0,"trim_fraction":.1,"hatta_trust_weight":.5,"client_participation":1.0,
           "local_optimizer":"fedavg","fedprox_mu":0.01,"samples":2400,"features":20}
    cfg.update(config or {})
    if (cfg["clients"] < 3 or cfg["rounds"] < 1 or cfg["local_epochs"] < 1 or cfg["batch_size"] < 1
            or cfg["learning_rate"] <= 0 or cfg["max_update_norm"] <= 0):
        raise ValueError("require >=3 clients and positive rounds, epochs, batch size, learning rate, and update norm")
    if cfg.get("local_optimizer", "fedavg") not in {"fedavg", "fedprox"} or not np.isfinite(float(cfg.get("fedprox_mu", 0.01))) or float(cfg.get("fedprox_mu", 0.01)) < 0:
        raise ValueError("local_optimizer must be fedavg or fedprox and fedprox_mu must be non-negative")
    if cfg["attack"] not in {"none", "label_flip", "scale", "sign", "slow",
                             "backdoor", "gaussian", "collusion", "model_replacement", "stale", "low_slow", "adaptive_mimic"}:
        raise ValueError("unsupported attack")
    if not 0 <= float(cfg["malicious_fraction"]) <= .5:
        raise ValueError("malicious_fraction must be in [0, 0.5]")
    if cfg["trust_evidence"] not in {"utility", "utility_integrity", "utility_integrity_temporal", "utility_heterogeneity"}:
        raise ValueError("unsupported trust_evidence ablation")
    if not 0 <= float(cfg["label_flip_fraction"]) <= 1 or float(cfg["benign_shift_strength"]) < 0:
        raise ValueError("label_flip_fraction and benign_shift_strength are out of range")
    if int(cfg["attack_start_round"]) < 1 or (cfg["attack_end_round"] is not None
            and int(cfg["attack_end_round"]) < int(cfg["attack_start_round"])):
        raise ValueError("attack rounds must use a positive inclusive start/end range")
    if cfg["detection_threshold"] is not None and np.isnan(float(cfg["detection_threshold"])):
        raise ValueError("detection_threshold cannot be NaN")
    if not 0 <= float(cfg["max_false_accusation_rate"]) <= 1:
        raise ValueError("max_false_accusation_rate must be in [0, 1]")
    if not 0 <= float(cfg["trust_recovery_rate"]) <= 1 or float(cfg["heterogeneity_weight"]) < 0:
        raise ValueError("trust_recovery_rate or heterogeneity_weight is out of range")
    if not 0 <= float(cfg["hatta_trust_weight"]) <= 1:
        raise ValueError("hatta_trust_weight must be in [0, 1]")
    if not 0 < float(cfg["client_participation"]) <= 1:
        raise ValueError("client_participation must be in (0, 1]")
    seed=int(cfg["seed"]); rng=np.random.default_rng(seed)
    groups = None
    split_type = "stratified_row"
    group_overlap = None
    if dataframe is None:
        x,y=make_classification(n_samples=int(cfg["samples"]),n_features=int(cfg["features"]),n_informative=max(2,int(cfg["features"]*.6)),
             n_redundant=2,weights=[.88,.12],class_sep=1.0,random_state=seed)
        data_source="generated research fixture (not real meter data)"
    else:
        if "is_theft" not in dataframe: raise ValueError("dataset requires is_theft target")
        excluded={"is_theft","seeded_theft_probability","theft_type","meter_id","timestamp","expected_consumption_kwh",
                  "wastage_score","wastage_flag","is_anomaly","theft_probability","risk_score","risk_level"}
        cols=[c for c in dataframe.select_dtypes(include=[np.number]).columns if c not in excluded]
        if not cols: raise ValueError("dataset has no numeric predictors")
        x=dataframe[cols].replace([np.inf,-np.inf],np.nan).to_numpy(dtype=np.float32); y=dataframe.is_theft.astype(int).to_numpy()
        if "meter_id" in dataframe: groups=dataframe.meter_id.astype(str).to_numpy()
        data_source="provided dataframe; meter-group holdout used when meter_id is present"
    if groups is not None and len(np.unique(groups)) >= 5:
        train_idx,test_idx=stratified_group_holdout(y,groups,test_size=.2,seed=seed)
        xtr,xte,ytr,yte=x[train_idx],x[test_idx],y[train_idx],y[test_idx]
        split_type = "customer_group_holdout"
        group_overlap = bool(set(groups[train_idx]) & set(groups[test_idx]))
    elif groups is not None:
        raise ValueError("customer-group split unavailable; use >=5 meters and >=2 meters per target class")
    else:
        xtr,xte,ytr,yte=train_test_split(x,y,test_size=.2,random_state=seed,stratify=y)
    # Validation is drawn only from training data, and is meter-disjoint whenever
    # meter IDs exist. Neither test rows nor test labels affect threshold selection.
    validation_group_overlap = None
    if groups is not None:
        fit_idx,validation_idx=stratified_group_holdout(ytr,groups[train_idx],test_size=.2,seed=seed+1)
        xfit_raw,xval_raw=xtr[fit_idx],xtr[validation_idx]
        ytrain,yval=ytr[fit_idx],ytr[validation_idx]
        validation_group_overlap=bool(set(groups[train_idx][fit_idx]) & set(groups[train_idx][validation_idx]))
    else:
        xfit_raw,xval_raw,ytrain,yval=train_test_split(xtr,ytr,test_size=.2,random_state=seed+1,stratify=ytr)
    # Fit imputation only on the training customers. Missingness indicators retain
    # information about meter/data outages without confusing missing readings with
    # genuine zero consumption. Validation/test values never influence imputer fit.
    imputer = SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True)
    xfit_imputed = imputer.fit_transform(xfit_raw)
    xval_imputed = imputer.transform(xval_raw)
    xte_imputed = imputer.transform(xte)
    scaler=StandardScaler().fit(xfit_imputed)
    xtrain=scaler.transform(xfit_imputed); xval=scaler.transform(xval_imputed); xte=scaler.transform(xte_imputed)
    partitions=partition_clients(ytrain,int(cfg["clients"]),str(cfg["partition"]),seed)
    d=xtrain.shape[1]+1; initial=np.zeros(d); global_weights={k:initial.copy() for k in ["fedavg","fedprox","fedavg_dp","trimmed_mean","multi_krum","trust","hatta"]}
    trust={p.client_id:.5 for p in partitions}; history={p.client_id:[] for p in partitions}; prev={p.client_id:None for p in partitions}
    malicious_count=max(1,int(len(partitions)*float(cfg["malicious_fraction"]))) if cfg["attack"]!="none" and float(cfg["malicious_fraction"])>0 else 0
    malicious=set(rng.choice([p.client_id for p in partitions],size=malicious_count,replace=False).tolist()) if malicious_count else set()
    shifted_count = int(np.ceil(len(partitions) * .25)) if float(cfg["benign_shift_strength"]) > 0 else 0
    shifted_clients=set([p.client_id for p in partitions if p.client_id not in malicious][-shifted_count:]) if shifted_count else set()
    client_scores={p.client_id:0.0 for p in partitions}; flagged_ever=set(); bad_streak={p.client_id:0 for p in partitions}
    collusion_direction=rng.normal(size=d)
    collusion_direction/=max(float(np.linalg.norm(collusion_direction)),1e-12)
    round_log=[]; bytes_sent=0; start=time.perf_counter(); successful=0
    method_names=list(global_weights)
    for rnd in range(int(cfg["rounds"])):
        attack_active=(rnd+1 >= int(cfg["attack_start_round"])
                       and (cfg["attack_end_round"] is None or rnd+1 <= int(cfg["attack_end_round"])))
        updates={name:[] for name in method_names}; sizes=[]; ids=[]; util=[]; integ=[]; temporal=[]; prior_scores=[]; norms=[]; harms=[]; class_spreads=[]; failed_ids=[]
        # Deterministic partial participation models availability/dropout. At least
        # three clients are retained so Byzantine aggregation remains meaningful.
        participant_count=max(3,int(np.ceil(len(partitions)*float(cfg["client_participation"]))))
        if participant_count >= len(partitions):
            round_partitions=partitions
        else:
            selected_indices=sorted(rng.choice(len(partitions),size=participant_count,replace=False).tolist())
            round_partitions=[partitions[i] for i in selected_indices]
        for part in round_partitions:
            idx=part.indices; xc,yc=xtrain[idx].copy(),ytrain[idx]
            if len(idx)<1: continue
            if part.client_id in shifted_clients and xc.shape[1]:
                # A benign covariate shift is a controlled non-IID condition, not an attack label.
                xc[:, 0] += float(cfg["benign_shift_strength"])
            # Data-poisoning simulation is isolated here from production prediction.
            local_y=yc.copy()
            if attack_active and part.client_id in malicious:
                attack_seed=seed+1009*rnd+int(part.client_id[-3:])
                if cfg["attack"]=="label_flip":
                    local_y=flip_labels(local_y,float(cfg["label_flip_fraction"]),attack_seed)
                elif cfg["attack"]=="backdoor":
                    xc,local_y=poison_backdoor(xc,local_y,fraction=float(cfg.get("backdoor_fraction",.2)),
                        trigger_value=float(cfg.get("backdoor_trigger_value",5.0)),
                        target_label=int(cfg.get("backdoor_target_label",1)),seed=attack_seed)
            client_updates={}; invalid=False
            try:
                for name in method_names:
                    base=global_weights[name]
                    delta=_fit(xc,local_y,base,int(cfg["local_epochs"]),float(cfg["learning_rate"]),int(cfg["batch_size"]),seed+rnd, prox_mu=(float(cfg["fedprox_mu"]) if name == "fedprox" else 0.0), global_parameters=base)-base
                    if attack_active and part.client_id in malicious:
                        intensity=float(cfg["attack_intensity"])
                        if cfg["attack"] in {"scale","sign","slow"}:
                            delta=manipulate_update(delta,str(cfg["attack"]),intensity)
                        elif cfg["attack"]=="gaussian":
                            delta=add_gaussian_update_noise(delta,std=intensity,seed=seed+7919*rnd+int(part.client_id[-3:]))
                        elif cfg["attack"]=="collusion":
                            delta=collude_update(delta,collusion_direction,intensity)
                        elif cfg["attack"]=="model_replacement":
                            delta=model_replacement_update(delta,scale=intensity*len(partitions)/max(1,malicious_count))
                        elif cfg["attack"]=="stale" and prev[part.client_id] is not None:
                            delta=prev[part.client_id].copy()
                    clipped,norm=_clip_update(delta,float(cfg["max_update_norm"]))
                    if clipped is None:
                        invalid=True
                        break
                    client_updates[name]=clipped
                    if name=="hatta": integrity_value=1.0 if norm<=float(cfg["max_update_norm"]) else float(np.clip(float(cfg["max_update_norm"])/max(norm,1e-12),0,1)); norm_value=norm
            except (ValueError, FloatingPointError, OverflowError):
                invalid=True
            if invalid:
                failed_ids.append(part.client_id)
                continue
            # Utility evidence is the change in log loss on validation data, not PR-AUC
            # rank movement. PR-AUC can improve under a sign reversal on imbalanced data.
            clipped=client_updates["hatta"]
            score_before=_binary_log_loss(global_weights["hatta"],xval,yval)
            candidate=global_weights["hatta"]+clipped
            score_after=_binary_log_loss(candidate,xval,yval)
            harm=validation_harm(score_before,score_after)
            harms.append(harm)
            subgroup_deltas=[]
            for label in np.unique(yval):
                mask=yval==label
                subgroup_deltas.append(_binary_log_loss(candidate,xval[mask],yval[mask])-
                                       _binary_log_loss(global_weights["hatta"],xval[mask],yval[mask]))
            class_spreads.append(float(np.std(subgroup_deltas)) if len(subgroup_deltas)>1 else 0.0)
            util.append(float(np.clip(1.0-harm/max(score_before,1e-8),0,1)))
            integ.append(integrity_value)
            old=prev[part.client_id]
            temporal.append(.5 if old is None else float(np.clip((1+np.dot(old,clipped)/(np.linalg.norm(old)*np.linalg.norm(clipped)+1e-12))/2,0,1)))
            prior_scores.append(trust[part.client_id]); norms.append(norm_value)
            prev[part.client_id]=clipped.copy()
            for name in method_names: updates[name].append(client_updates[name])
            sizes.append(len(idx)); ids.append(part.client_id)
        if not ids: raise RuntimeError("all clients failed")
        # The threshold is derived only from internal validation observations,
        # unless a threshold calibrated on independent validation seeds is supplied.
        integrity_risk=np.maximum(0.0,np.asarray(norms)/float(cfg["max_update_norm"])-1.0)
        temporal_risk=1.0-np.asarray(temporal)
        evidence=np.asarray(harms,dtype=float)
        if cfg["trust_evidence"] in {"utility_integrity", "utility_integrity_temporal"}:
            evidence=evidence+integrity_risk*max(float(np.median(harms)),.01)
        if cfg["trust_evidence"] == "utility_integrity_temporal":
            evidence=evidence+temporal_risk*max(float(np.median(harms)),.01)
        if cfg["trust_evidence"] == "utility_heterogeneity":
            # If validation subgroups move in opposite directions, shrink the
            # accusation score: a single global utility can hide client shift.
            evidence=np.maximum(0.0,evidence-float(cfg["heterogeneity_weight"])*np.asarray(class_spreads))
        dynamic_threshold=robust_validation_threshold(evidence.tolist(),float(cfg["trust_mad_multiplier"]))
        threshold=float(cfg["detection_threshold"]) if cfg["detection_threshold"] is not None else dynamic_threshold
        scale=max(float(np.median(np.abs(evidence))),.01)
        newtrust=[]
        for i,cid in enumerate(ids):
            client_scores[cid]=max(client_scores[cid],float(evidence[i]))
            if bool(cfg.get("trust_dp_enabled", False)):
                # Release only a bounded 3-component evidence vector with Gaussian noise.
                raw_evidence=np.clip(np.asarray([util[i],integ[i],temporal[i]],dtype=float),0.0,1.0)
                sensitivity=np.sqrt(3.0)
                sigma=float(cfg["trust_dp_noise_multiplier"])*sensitivity
                rng_private=np.random.default_rng(seed+900001+rnd*10007+i)
                private_evidence=np.clip(raw_evidence+rng_private.normal(0.0,sigma,size=3),0.0,1.0)
                utility_value,integrity_value_private,temporal_value_private=private_evidence.tolist()
            else:
                utility_value,integrity_value_private,temporal_value_private=util[i],integ[i],temporal[i]
            raw_bad=bool(evidence[i] > threshold)
            bad_streak[cid]=bad_streak[cid]+1 if raw_bad else 0
            is_flagged=bool(bad_streak[cid] >= int(cfg.get("trust_bad_round_patience",2)))
            if is_flagged:
                flagged_ever.add(cid)
                trust[cid]=max(.01,trust[cid]*float(np.exp(-max(evidence[i]-threshold,0.0)/scale)))
            else:
                # Recovery is gradual and uses measured, optionally privatized evidence.
                trust[cid]=update_trust(trust[cid],utility_value,integrity_value_private,
                    temporal_value_private,recovery=float(cfg["trust_recovery_rate"]))
            history[cid].append(trust[cid]); newtrust.append(trust[cid])
        round_weights=normalized_weights(newtrust,sizes)
        decisions=[{"client_id":cid,"trust_before":prior_scores[i],"trust_after":newtrust[i],"validation_utility":util[i],
                    "integrity":integ[i],"temporal_consistency":temporal[i],"update_norm_before_clip":norms[i],
                    "validation_harm":harms[i],"validation_subgroup_harm_spread":class_spreads[i],
                    "detection_score":float(evidence[i]),"detection_threshold":threshold,
                    "aggregation_weight":float(round_weights[i]),"suspicion_streak":int(bad_streak[cid]),"decision":"flagged_downweighted" if bad_streak[cid]>=int(cfg.get("trust_bad_round_patience",2)) else "included_clipped"}
                   for i,cid in enumerate(ids)]
        active_malicious_count=len(set(ids).intersection(malicious))
        krum_f = min(active_malicious_count, max(0, (len(ids)-3)//2))
        methods={"fedavg":fedavg(updates["fedavg"],sizes),
                 "fedprox":fedavg(updates["fedprox"],sizes),
                 "fedavg_dp":(gaussian_dp_aggregate(updates["fedavg_dp"],max_norm=float(cfg.get("dp_clip_norm",5.0)),
                     noise_multiplier=float(cfg.get("dp_noise_multiplier",1.5)),delta=float(cfg.get("dp_delta",1e-5)),
                     seed=int(cfg["seed"])+100000+rnd)["aggregate"] if bool(cfg.get("dp_enabled",False))
                     else fedavg(updates["fedavg_dp"],sizes)),
                 "multi_krum":multi_krum(updates["multi_krum"],byzantine_clients=krum_f),
                 "trimmed_mean":trimmed_mean(updates["trimmed_mean"],float(cfg["trim_fraction"])),
                 "trust":trust_weighted(updates["trust"],sizes,newtrust),
                 "hatta":(float(cfg["hatta_trust_weight"])*trust_weighted(updates["hatta"],sizes,newtrust)
                         +(1.0-float(cfg["hatta_trust_weight"]))*trimmed_mean(updates["hatta"],float(cfg["trim_fraction"])))}
        for name,delta in methods.items(): global_weights[name]+=delta
        # Report per-method communication for an equivalent deployment; four methods are compared offline.
        bytes_sent += sum(u.nbytes for u in updates["fedavg"])*2; successful += len(ids)
        round_log.append({"round":rnd+1,"participants":len(ids),"mean_trust":float(np.mean(newtrust)),"communication_bytes_cumulative":bytes_sent,
                          "validation_pr_auc":{m:_metrics(w,xval,yval)["pr_auc"] for m,w in global_weights.items()},
                           "trust_decisions":decisions,"failed_clients":failed_ids,"detection_threshold":threshold,
                           "attacking_clients":sorted(malicious) if attack_active else []})
    elapsed=time.perf_counter()-start
    centralized=_fit(xtrain,ytrain,initial,int(cfg["rounds"])*int(cfg["local_epochs"]),float(cfg["learning_rate"]),int(cfg["batch_size"]),seed)
    local_models={p.client_id:_fit(xtrain[p.indices],ytrain[p.indices],initial,int(cfg["rounds"])*int(cfg["local_epochs"]),float(cfg["learning_rate"]),int(cfg["batch_size"]),seed) for p in partitions}
    metrics={"centralized":_metrics(centralized,xte,yte),"local_only":{cid:_metrics(w,xte,yte) for cid,w in local_models.items()},
             **{m:_metrics(w,xte,yte) for m,w in global_weights.items() if m != "fedavg_dp" or bool(cfg.get("dp_enabled",False))}}
    backdoor_success_rate = None
    if cfg["attack"] == "backdoor":
        triggered_test = xte.copy()
        triggered_test[:, 0] = float(cfg.get("backdoor_trigger_value", 5.0))
        triggered_predictions = (_sigmoid(triggered_test @ global_weights["hatta"][:-1] +
                                           global_weights["hatta"][-1]) >= .5).astype(int)
        backdoor_success_rate = float((triggered_predictions == int(cfg.get("backdoor_target_label", 1))).mean())
    malicious_detected=flagged_ever
    tp=len(malicious & malicious_detected); fp=len(malicious_detected-malicious); fn=len(malicious-malicious_detected)
    result={"config":cfg,"data_source":data_source,"split":{"strategy":split_type,"test_group_overlap":group_overlap,
              "validation_group_overlap":validation_group_overlap},
            "privacy":({"enabled":True,"status":"research_client_level_dp_enabled",
              **compose_gaussian_rdp(noise_multiplier=float(cfg.get("dp_noise_multiplier",1.5)),
                    rounds=int(cfg["rounds"]),delta=float(cfg.get("dp_delta",1e-5))),
              "clipping_norm":float(cfg.get("dp_clip_norm",5.0)),
              "adjacency":"replacement of one client update per round",
              "limitations":"Full-participation conservative RDP composition; assumes each round releases one clipped noisy mean. Does not cover all API logs, checkpoints, dashboards, raw data or other model releases."}
              if bool(cfg.get("dp_enabled",False)) else
              {"enabled":False,"status":"disabled","reason":"Set dp_enabled=true to run the client-update Gaussian mechanism and full-participation RDP accounting."}),
            "trust_privacy":({"enabled":True,"scope":"bounded utility/integrity/temporal evidence vector only",
                **compose_gaussian_rdp(noise_multiplier=float(cfg.get("trust_dp_noise_multiplier",2.0)),
                    rounds=int(cfg["rounds"]),delta=float(cfg.get("dp_delta",1e-5))),
                "sensitivity_l2":float(np.sqrt(3.0)),
                "limitations":"This does not make HATTA end-to-end differentially private: raw updates and validation-derived harms are still processed by the coordinator. It protects only the separately noised trust-evidence vector under the stated Gaussian mechanism."}
                if bool(cfg.get("trust_dp_enabled",False)) else
                {"enabled":False,"status":"disabled"}),
            "metrics":metrics,"security":{"malicious_clients":sorted(malicious),"flagged_clients":sorted(malicious_detected),
              "detection_precision":tp/max(1,tp+fp),"detection_recall":tp/max(1,tp+fn),"honest_false_accusation_rate":fp/max(1,len(partitions)-len(malicious)),
              "client_scores":client_scores,"threshold_source":"calibrated_validation" if cfg["detection_threshold"] is not None else "round_validation_median_mad",
              "shifted_benign_clients":sorted(shifted_clients),"attack":"label_flip/scale/sign/slow/backdoor/gaussian/collusion/model_replacement/stale/low_slow/adaptive_mimic supported; run config selects one",
              "attack_success_rate":backdoor_success_rate,
             "attack_impact":None},
             "trust_history":history,"clients":[{"client_id":p.client_id,"samples":int(len(p.indices)),"positive_rate":float(ytrain[p.indices].mean()),"trust":trust[p.client_id]} for p in partitions],
             "recovery":{"measured":bool(malicious and cfg["attack_end_round"] is not None
                                             and int(cfg["attack_end_round"])<int(cfg["rounds"])),
                         "attack_end_round":cfg["attack_end_round"],
                         "attacker_trust_after_attack":{cid:history[cid][int(cfg["attack_end_round"])-1]
                                                        for cid in malicious if cfg["attack_end_round"] is not None
                                                        and len(history[cid])>=int(cfg["attack_end_round"])},
                         "attacker_final_trust":{cid:trust[cid] for cid in malicious}},
            "rounds":round_log,"efficiency":{"training_seconds":elapsed,"communication_bytes":bytes_sent,"rounds":int(cfg["rounds"]),"messages":successful*2,
                "client_participation":float(cfg["client_participation"]),
                "mean_participants_per_round":float(np.mean([r["participants"] for r in round_log]))},
            "method":{"name":"HATTA (provisional)","equation":"validation log-loss harm with robust validation-only threshold; flagged updates are downweighted; aggregation=hatta_trust_weight * trust-weighted clipped update + (1-hatta_trust_weight) * coordinate trimmed mean",
              "trust_evidence":cfg["trust_evidence"],"validation":"internal split of training partition; final test reserved"}}
    if output_dir is not None:
        out=Path(output_dir); out.mkdir(parents=True,exist_ok=True)
        (out/"config.json").write_text(json.dumps(cfg,indent=2),encoding="utf-8")
        (out/"results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        (out/"rounds.jsonl").write_text("\n".join(json.dumps(x) for x in round_log),encoding="utf-8")
        np.savez_compressed(out/"checkpoints.npz",**global_weights)
    return result


def run_calibrated_study(*, calibration_seeds: list[int], evaluation_seeds: list[int],
                         scenarios: list[dict[str, Any]] | None = None,
                         config: dict[str, Any] | None = None,
                         evidence_ablations: tuple[str, ...] = ("utility", "utility_integrity", "utility_integrity_temporal", "utility_heterogeneity"),
                         max_false_accusation_rate: float = .10) -> dict[str, Any]:
    """Run leave-one-attack-family-out calibration and disjoint seed evaluation.

    Thresholds for an evaluation family are calibrated on other families and
    separate seeds. Simulated attack labels are used only for calibration.
    The fixed evidence modes are ablations, not chosen from evaluation data.
    """
    if not calibration_seeds or not evaluation_seeds:
        raise ValueError("calibration_seeds and evaluation_seeds must be non-empty")
    if set(calibration_seeds) & set(evaluation_seeds):
        raise ValueError("calibration and evaluation seeds must be disjoint")
    if not 0 <= max_false_accusation_rate <= 1:
        raise ValueError("max_false_accusation_rate must be in [0, 1]")
    if scenarios is None:
        scenarios = [
            {"name":"benign_iid","attack":"none","malicious_fraction":0.0,"partition":"iid"},
            {"name":"benign_moderate","attack":"none","malicious_fraction":0.0,"partition":"moderate"},
            {"name":"benign_severe","attack":"none","malicious_fraction":0.0,"partition":"severe"},
            {"name":"sign_25","attack":"sign","malicious_fraction":0.25,"partition":"severe"},
            {"name":"sign_50","attack":"sign","malicious_fraction":0.50,"partition":"severe"},
            {"name":"scale_2x_25","attack":"scale","attack_intensity":2.0,"malicious_fraction":0.25,"partition":"severe"},
            {"name":"scale_4x_25","attack":"scale","attack_intensity":4.0,"malicious_fraction":0.25,"partition":"severe"},
            {"name":"scale_8x_25","attack":"scale","attack_intensity":8.0,"malicious_fraction":0.25,"partition":"severe"},
            {"name":"scale_4x_50","attack":"scale","attack_intensity":4.0,"malicious_fraction":0.50,"partition":"severe"},
            {"name":"scale_4x_clip_1","attack":"scale","attack_intensity":4.0,"malicious_fraction":0.25,"partition":"severe","max_update_norm":1.0},
            {"name":"scale_4x_no_clip","attack":"scale","attack_intensity":4.0,"malicious_fraction":0.25,"partition":"severe","max_update_norm":1000000.0},
            {"name":"label_flip_25","attack":"label_flip","malicious_fraction":0.25,"partition":"severe"},
            {"name":"label_flip_50","attack":"label_flip","malicious_fraction":0.50,"partition":"severe"},
            {"name":"benign_shift_moderate","attack":"none","malicious_fraction":0.0,"partition":"moderate","benign_shift_strength":1.5},
            {"name":"benign_shift_severe","attack":"none","malicious_fraction":0.0,"partition":"severe","benign_shift_strength":1.5},
            {"name":"temporary_sign","attack":"sign","malicious_fraction":0.25,"partition":"severe","attack_end_round":1},
            {"name":"temporary_sign_no_recovery","attack":"sign","malicious_fraction":0.25,"partition":"severe","attack_end_round":1,"trust_recovery_rate":0.0},
        ]
    names=[str(scenario["name"]) for scenario in scenarios]
    if len(names) != len(set(names)):
        raise ValueError("scenario names must be unique")
    common = dict(config or {})
    methods=("fedavg","fedprox","trimmed_mean","multi_krum","trust","hatta")
    modes={"utility":0,"utility_integrity":1,"utility_integrity_temporal":2,"utility_heterogeneity":3}
    if any(mode not in modes for mode in evidence_ablations):
        raise ValueError("unknown trust evidence ablation")
    report: dict[str, Any]={"calibration_seeds":calibration_seeds,"evaluation_seeds":evaluation_seeds,
        "configuration":common,"scenario_configurations":scenarios,"aggregation_methods":methods,
        "scenarios":{},"calibration":{},"evidence_ablations":list(evidence_ablations),
        "primary_evidence":"utility (pre-specified; other modes are ablations)",
        "threshold_protocol":{"kind":"leave_one_attack_family_out","thresholds_fit_on":"internal validation harms and simulated calibration attack labels",
            "attack_family_excluded_from_its_threshold":True,"seed_sets_disjoint":True,
            "max_calibration_honest_false_accusation_rate":max_false_accusation_rate},
        "attack_success_rate":"not defined for these untargeted attacks; paired metric impact is reported"}
    scenario_reports={mode:{} for mode in evidence_ablations}
    raw_results={mode:{} for mode in evidence_ablations}
    calibration_reports={mode:{} for mode in evidence_ablations}
    thresholds: dict[tuple[str,str],float]={}
    calibration_cache: dict[tuple[str,str],dict[str,Any]]={}
    def scenario_family(scenario: dict[str,Any]) -> str:
        attack=str(scenario.get("attack","none"))
        if attack != "none":
            return attack
        return "benign_shift" if float(scenario.get("benign_shift_strength",0.0))>0 else "benign"
    family_representatives: dict[str,dict[str,Any]]={}
    for scenario in scenarios:
        family= scenario_family(scenario)
        family_representatives.setdefault(family,scenario)
    for target in scenarios:
        target_name=str(target["name"])
        target_family=scenario_family(target)
        calibration_scenarios=[s for family,s in family_representatives.items() if family != target_family]
        if not calibration_scenarios:
            raise ValueError(f"no independent scenario family available to calibrate {target_name}")
        for mode in evidence_ablations:
            cache_key=(mode,target_family)
            if cache_key not in calibration_cache:
                scores: list[float]=[]; labels: list[bool]=[]
                for scenario in calibration_scenarios:
                    for seed in calibration_seeds:
                        run_cfg={**common,**scenario,"seed":seed,"trust_evidence":mode,
                            "detection_threshold":float("inf"),"max_false_accusation_rate":max_false_accusation_rate}
                        calibration_run=run_experiment(run_cfg)
                        attackers=set(calibration_run["security"]["malicious_clients"])
                        for client_id,score in calibration_run["security"]["client_scores"].items():
                            scores.append(float(score)); labels.append(client_id in attackers)
                if not any(labels) or all(labels):
                    raise ValueError(f"calibration for family {target_family} needs both benign and attacked client examples")
                threshold=select_detection_threshold(scores,labels,max_false_accusation_rate=max_false_accusation_rate)
                values=np.asarray(scores); truth=np.asarray(labels,dtype=bool); predictions=values>threshold
                tp=int(np.sum(predictions&truth)); fp=int(np.sum(predictions&~truth))
                calibration_cache[cache_key]={"threshold":threshold,
                    "calibration_scenarios":[str(s["name"]) for s in calibration_scenarios],"client_observations":len(scores),
                    "precision":tp/max(1,tp+fp),"recall":tp/max(1,int(truth.sum())),
                    "honest_false_accusation_rate":float(np.mean(predictions[~truth])) if (~truth).any() else 0.0}
            thresholds[(mode,target_name)]=float(calibration_cache[cache_key]["threshold"])
            calibration_reports[mode][target_name]={**calibration_cache[cache_key],"excluded_attack_family":target_family}

    for scenario in scenarios:
        name=str(scenario["name"])
        for mode in evidence_ablations:
            runs=[]
            threshold=thresholds[(mode,name)]
            for seed in evaluation_seeds:
                run_cfg={**common,**scenario,"seed":seed,"trust_evidence":mode,
                    "detection_threshold":threshold,"max_false_accusation_rate":max_false_accusation_rate}
                runs.append(run_experiment(run_cfg))
            raw_results[mode][name]=runs
            metric_summaries={method:{metric:_summary_stats([float(run["metrics"][method][metric]) for run in runs])
                for metric in ("accuracy","precision","recall","f1","pr_auc","false_positive_rate")}
                for method in methods}
            detection_fields={"precision":"detection_precision","recall":"detection_recall",
                              "honest_false_accusation_rate":"honest_false_accusation_rate"}
            detection_summary={key:_summary_stats([float(run["security"][field]) for run in runs])
                               for key,field in detection_fields.items()}
            client_ids=sorted(runs[0]["metrics"]["local_only"])
            per_client={cid:{metric:_summary_stats([float(run["metrics"]["local_only"][cid][metric]) for run in runs])
                for metric in ("precision","recall","f1","pr_auc","false_positive_rate")} for cid in client_ids}
            recovery_values=[float(trust) for run in runs for trust in run["recovery"]["attacker_final_trust"].values()]
            report_item={"seeds":evaluation_seeds,
                "detection_mean":{"precision":detection_summary["precision"]["mean"],"recall":detection_summary["recall"]["mean"],
                                  "honest_false_accusation_rate":detection_summary["honest_false_accusation_rate"]["mean"]},
                "detection_statistics":detection_summary,
                "metrics":{method:{metric:summary["mean"] for metric,summary in values.items()}
                           for method,values in metric_summaries.items()},
                "metric_statistics":metric_summaries,"per_client_local_only_metrics":per_client,
                "threshold":threshold,"attack_success_rate":None,
                "recovery_final_trust":_summary_stats(recovery_values) if recovery_values else None,
                "run_details":[{"seed":run["config"]["seed"],"metrics":run["metrics"],
                    "security":run["security"],"trust_history":run["trust_history"],
                    "rounds":run["rounds"],"recovery":run["recovery"],"clients":run["clients"],
                    "efficiency":run["efficiency"],"split":run["split"]} for run in runs]}
            scenario_reports[mode][name]=report_item

    # Compare each attacked run with the matching clean partition severity and seed.
    for mode in evidence_ablations:
        for scenario in scenarios:
            if scenario.get("attack","none")=="none":
                continue
            name=str(scenario["name"]); partition=str(scenario.get("partition",common.get("partition","moderate")))
            baseline_name=f"benign_{partition}"
            if baseline_name not in raw_results[mode]:
                continue
            attacked=raw_results[mode][name]; baseline=raw_results[mode][baseline_name]
            scenario_reports[mode][name]["paired_pr_auc_impact"]={method:_summary_stats([
                float(base["metrics"][method]["pr_auc"]-attack["metrics"][method]["pr_auc"])
                for base,attack in zip(baseline,attacked)],bounds=(-1.0,1.0)) for method in methods}
    report["calibration"]=calibration_reports
    report["scenarios"]=scenario_reports
    return report
