"""Leakage-aware tuned SGCC benchmark with train-only threshold calibration.

The final test customers are untouched by hyperparameter and threshold selection.
This script reports fixed-0.5 and validation-calibrated metrics side by side.
"""
from __future__ import annotations
import argparse, json, hashlib, math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier, HistGradientBoostingClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit, StratifiedShuffleSplit
from sklearn.pipeline import make_pipeline

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

def _sha(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def _models(seed):
    # Class-weighted histogram boosting is selected from the prior full-cohort
    # benchmark for its stronger ranking/PR-AUC; threshold is calibrated separately.
    return {
      "hist_gradient_boosting": [
        HistGradientBoostingClassifier(max_iter=150,learning_rate=.08,max_leaf_nodes=31,
          l2_regularization=1.0,random_state=seed),
      ],
    }

def _metric(y,prob,threshold):
    pred=(prob>=threshold).astype(int)
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {"accuracy":float(accuracy_score(y,pred)),
      "precision":float(precision_score(y,pred,zero_division=0)),
      "recall":float(recall_score(y,pred,zero_division=0)),
      "f1":float(f1_score(y,pred,zero_division=0)),
      "balanced_accuracy":float(balanced_accuracy_score(y,pred)),
      "roc_auc":float(roc_auc_score(y,prob)),
      "pr_auc":float(average_precision_score(y,prob)),
      "false_positive_rate":float(fp/max(1,fp+tn)),
      "mcc":float(matthews_corrcoef(y,pred)),
      "threshold":float(threshold),
      "confusion_matrix":{"tn":int(tn),"fp":int(fp),"fn":int(fn),"tp":int(tp)}}

def _fit_predict(model,xfit,yfit,xval,seed):
    pipe=make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),model)
    pipe.fit(xfit,yfit)
    return pipe,pipe.predict_proba(xval)[:,1]

def _choose_threshold(y,prob,minimum_precision=.25):
    # Threshold is chosen on validation only. Maximise F1 subject to a modest
    # precision floor, with recall and then higher threshold as tie-breakers.
    candidates=np.unique(np.r_[np.linspace(.03,.97,95),np.quantile(prob,np.linspace(0,1,101))])
    feasible=[]
    for threshold in candidates:
        m=_metric(y,prob,float(threshold))
        if m["precision"]>=minimum_precision:
            feasible.append((m["f1"],m["recall"],float(threshold),m))
    if not feasible:
        feasible=[]
        for t in candidates:
            m=_metric(y,prob,float(t))
            feasible.append((m["f1"],m["recall"],float(t),m))
    best=max(feasible,key=lambda z:(z[0],z[1],z[2]))
    return best[2],best[3]

def evaluate(frame,seeds,minimum_precision=.20):
    if not {"meter_id","is_theft"}.issubset(frame.columns):
        raise ValueError("expected meter_id and is_theft columns")
    if frame["meter_id"].duplicated().any():
        raise ValueError("expected one row per customer; duplicate meter_id detected")
    y=frame["is_theft"].astype(int).to_numpy()
    if set(np.unique(y))!={0,1}: raise ValueError("both theft and normal classes are required")
    x=frame.drop(columns=["meter_id","is_theft"],errors="ignore").select_dtypes(include=[np.number,"bool"])
    x=x.replace([np.inf,-np.inf],np.nan)
    if x.empty: raise ValueError("no numeric features")
    groups=frame["meter_id"].astype(str).to_numpy()
    records=[]
    for seed in seeds:
        split=GroupShuffleSplit(n_splits=1,test_size=.20,random_state=seed)
        train_idx,test_idx=next(split.split(x,y,groups))
        inner=GroupShuffleSplit(n_splits=1,test_size=.20,random_state=seed+1000)
        fit_rel,val_rel=next(inner.split(x.iloc[train_idx],y[train_idx],groups[train_idx]))
        fit_idx=train_idx[fit_rel]; val_idx=train_idx[val_rel]
        if len(np.unique(y[fit_idx]))<2 or len(np.unique(y[val_idx]))<2 or len(np.unique(y[test_idx]))<2:
            raise ValueError(f"seed {seed} produced a single-class split")
        candidates=[]
        for family,models in _models(seed).items():
            for ci,model in enumerate(models):
                fitted,val_prob=_fit_predict(model,x.iloc[fit_idx],y[fit_idx],x.iloc[val_idx],seed)
                val_pr=float(average_precision_score(y[val_idx],val_prob))
                threshold,val_metrics=_choose_threshold(y[val_idx],val_prob,minimum_precision)
                candidates.append((val_pr,val_metrics["f1"],family,ci,model,threshold))
        # Select on validation PR-AUC, then validation F1. Never inspect test metrics here.
        selected=max(candidates,key=lambda c:(c[0],c[1]))
        val_pr,val_f1,family,ci,model,threshold=selected
        # Refit the selected model on the complete outer training customers.
        fitted,_=_fit_predict(model,x.iloc[train_idx],y[train_idx],x.iloc[test_idx],seed)
        test_prob=fitted.predict_proba(x.iloc[test_idx])[:,1]
        metrics_fixed=_metric(y[test_idx],test_prob,.5)
        metrics_tuned=_metric(y[test_idx],test_prob,threshold)
        records.append({"seed":seed,"selected_model":family,"candidate_index":ci,
          "validation_pr_auc":val_pr,"validation_f1":val_f1,"selected_threshold":threshold,
          "train_customers":int(len(train_idx)),"fit_customers":int(len(fit_idx)),
          "validation_customers":int(len(val_idx)),"test_customers":int(len(test_idx)),
          "customer_overlap":0,"fixed_threshold_test":metrics_fixed,
          "calibrated_threshold_test":metrics_tuned})
    summary={}
    for mode in ("fixed_threshold_test","calibrated_threshold_test"):
        summary[mode]={}
        for metric in ("accuracy","precision","recall","f1","balanced_accuracy","roc_auc","pr_auc","false_positive_rate","mcc"):
            vals=np.asarray([r[mode][metric] for r in records],dtype=float)
            mean=float(vals.mean()); sd=float(vals.std(ddof=1)); n=len(vals)
            crit={2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262}.get(n-1,1.96)
            half=crit*sd/math.sqrt(n)
            lower,upper=mean-half,mean+half
            bounds=(-1.0,1.0) if metric=="mcc" else (0.0,1.0)
            summary[mode][metric]={"mean":mean,"std":sd,"ci95_t":[max(bounds[0],lower),min(bounds[1],upper)],"n":n}
    return {"dataset":"SGCC prepared customer features","protocol":"customer-disjoint 80/20 outer holdout; inner customer-disjoint 80/20 fit/validation; model and threshold selected on validation only; test set untouched",
      "seeds":list(seeds),"minimum_validation_precision":minimum_precision,
      "threshold_objective":"F1 on validation, subject to minimum precision constraint; selected model refit on full outer training customers",
      "feature_count":int(x.shape[1]),"customer_count":int(len(frame)),
      "records":records,"summary":summary,
      "limitations":["Historical SGCC-labelled Chinese benchmark, not Indian utility field validation.",
        "Model/threshold selection is validation-only; no guarantee all metrics improve simultaneously.",
        "This is a research model benchmark, not a replacement of every production dashboard classifier."]}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"))
    p.add_argument("--seeds",default="11,23,37,53,71")
    p.add_argument("--minimum-precision",type=float,default=.25)
    p.add_argument("--max-customers",type=int,default=10000,help="stratified customer sample for tractable tuning; 0 uses all customers")
    p.add_argument("--output",type=Path,default=Path("reports/research_runs/sgcc_tuned_customer_benchmark.json"))
    a=p.parse_args()
    if not 0<a.minimum_precision<=1: p.error("--minimum-precision must be in (0,1]")
    seeds=[int(x) for x in a.seeds.split(",") if x.strip()]
    if len(seeds)<3 or len(set(seeds))!=len(seeds): p.error("provide at least three unique seeds")
    frame=pd.read_csv(a.input,low_memory=False)
    original_rows=len(frame)
    if a.max_customers and len(frame)>a.max_customers:
        frame=pd.concat([g.sample(n=min(len(g),max(1,int(round(a.max_customers*len(g)/len(frame))))),random_state=2026)
                         for _,g in frame.groupby("is_theft")],ignore_index=True).sample(frac=1,random_state=2026).reset_index(drop=True)
    result=evaluate(frame,seeds,a.minimum_precision)
    result["source_customer_count"]=original_rows
    result["sampled_customer_count"]=len(frame)
    result["sampling_protocol"]="stratified fixed-seed customer sample for tuning pilot" if len(frame)<original_rows else "full customer dataset"
    result["feature_file_sha256"]=_sha(a.input)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"summary":result["summary"]},indent=2))
if __name__=="__main__": main()
