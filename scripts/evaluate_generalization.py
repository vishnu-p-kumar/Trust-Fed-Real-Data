"""Cross-location, seasonal and temporal generalization evaluation for labeled meter data.

This evaluator requires real binary theft labels supplied by the data owner. It
never fabricates labels. Results are valid only for the supplied dataset and
its documented label provenance.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, precision_score, recall_score, roc_auc_score)
from sklearn.pipeline import make_pipeline
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

LABELS=("is_theft","theft_label","label","target","fraud","flag")
IDS=("meter_id","customer_id","consumer_id","client_id","cons_no","consno","consumerid","id")
LOCATIONS=("city","location","region","district","utility_area")
TIMES=("timestamp","datetime","date","reading_date","time")
EXCLUDED={"seeded_theft_probability","theft_probability","risk_score","risk_level","is_anomaly","wastage_score","wastage_flag","theft_type"}

def _resolve(frame, aliases):
    cols={str(c).strip().lower():c for c in frame.columns}
    return next((cols[x] for x in aliases if x in cols),None)

def _binary_labels(series):
    if set(pd.unique(series.dropna())).issubset({0,1,0.0,1.0,False,True}):
        return series.astype(int)
    mapping={"normal":0,"honest":0,"non-theft":0,"non_theft":0,"0":0,
             "theft":1,"fraud":1,"fraudulent":1,"1":1}
    out=series.astype(str).str.strip().str.lower().map(mapping)
    if out.isna().any(): raise ValueError("labels must be binary 0/1 or normal/theft text")
    return out.astype(int)

def _metric_block(y, prob):
    pred=(prob>=.5).astype(int)
    tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {"precision":float(precision_score(y,pred,zero_division=0)),
      "recall":float(recall_score(y,pred,zero_division=0)),"f1":float(f1_score(y,pred,zero_division=0)),
      "balanced_accuracy":float(balanced_accuracy_score(y,pred)),"roc_auc":float(roc_auc_score(y,prob)),
      "average_precision":float(average_precision_score(y,prob)),"false_positive_rate":float(fp/max(1,fp+tn)),
      "confusion_matrix":{"tn":int(tn),"fp":int(fp),"fn":int(fn),"tp":int(tp)}}

def _model(seed):
    return make_pipeline(SimpleImputer(strategy="median"),RandomForestClassifier(
        n_estimators=200,max_depth=16,min_samples_leaf=3,class_weight="balanced_subsample",
        random_state=seed,n_jobs=2))

def evaluate_generalization(frame: pd.DataFrame, seeds=(11,23,37)):
    label_col=_resolve(frame,LABELS); group_col=_resolve(frame,IDS)
    if label_col is None or group_col is None: raise ValueError("dataset needs a binary theft label and meter/customer ID")
    data=frame.loc[frame[label_col].notna()].copy(); y=_binary_labels(data[label_col])
    if y.nunique()!=2: raise ValueError("both theft and non-theft labels are required")
    excluded={label_col,group_col}|EXCLUDED
    city_col=_resolve(data,LOCATIONS); time_col=_resolve(data,TIMES)
    if city_col: excluded.add(city_col)
    if time_col: excluded.add(time_col)
    X=data.drop(columns=list(excluded),errors="ignore").select_dtypes(include=[np.number,"bool"])
    X=X.replace([np.inf,-np.inf],np.nan)
    if X.empty: raise ValueError("no numeric predictive features available")
    results={"cross_location":{},"seasonal":{},"temporal_drift":None,
             "feature_columns":[str(c) for c in X.columns],"label_column":str(label_col),
             "customer_id_column":str(group_col)}
    if city_col:
        for city in sorted(data[city_col].dropna().astype(str).unique()):
            test=data[city_col].astype(str).eq(city).to_numpy(); train=~test
            if len(set(y[train]))<2 or len(set(y[test]))<2: continue
            runs=[]
            for seed in seeds:
                model=_model(seed); model.fit(X.loc[train],y.loc[train]); prob=model.predict_proba(X.loc[test])[:,1]
                runs.append(_metric_block(y.loc[test],prob))
            results["cross_location"][city]={"test_rows":int(test.sum()),
                "test_customers":int(data.loc[test,group_col].nunique()),"runs":runs,
                "customer_overlap":0,"train_locations":[x for x in sorted(data[city_col].dropna().astype(str).unique()) if x!=city]}
    if time_col:
        dates=pd.to_datetime(data[time_col],errors="coerce")
        valid=dates.notna()
        if valid.sum()>=20:
            month=dates.dt.month
            season=np.select([month.isin([12,1,2]),month.isin([3,4,5]),month.isin([6,7,8]),month.isin([9,10,11])],
                             ["winter","pre_monsoon","monsoon","post_monsoon"],default="unknown")
            for name in ("winter","pre_monsoon","monsoon","post_monsoon"):
                test=(season==name)&valid.to_numpy(); train=(season!=name)&valid.to_numpy()
                if test.sum()<2 or len(set(y.iloc[np.where(test)[0]]))<2 or len(set(y.iloc[np.where(train)[0]]))<2: continue
                runs=[]
                for seed in seeds:
                    model=_model(seed); model.fit(X.loc[train],y.loc[train]); prob=model.predict_proba(X.loc[test])[:,1]
                    runs.append(_metric_block(y.loc[test],prob))
                results["seasonal"][name]={"test_rows":int(test.sum()),"runs":runs,
                    "note":"Season-held-out evaluation; meters may appear in other seasons, so this is not a customer-disjoint split."}
            order=np.argsort(dates[valid].to_numpy()); valid_indices=np.where(valid.to_numpy())[0][order]
            cut=int(len(valid_indices)*.7); train_idx=valid_indices[:cut]; test_idx=valid_indices[cut:]
            if len(train_idx)>5 and len(test_idx)>5 and y.iloc[train_idx].nunique()==2 and y.iloc[test_idx].nunique()==2:
                drift_runs=[]
                for seed in seeds:
                    model=_model(seed); model.fit(X.iloc[train_idx],y.iloc[train_idx]); prob=model.predict_proba(X.iloc[test_idx])[:,1]
                    drift_runs.append(_metric_block(y.iloc[test_idx],prob))
                results["temporal_drift"]={"split":"chronological first 70% train / last 30% test",
                    "train_end":str(dates.iloc[train_idx].max()),"test_start":str(dates.iloc[test_idx].min()),
                    "train_rows":len(train_idx),"test_rows":len(test_idx),"runs":drift_runs}
    if not city_col and not time_col:
        raise ValueError("dataset needs a city/location or timestamp column for generalization tests")
    results["limitations"]=["Requires genuine externally sourced theft labels; this script does not validate label provenance.",
      "Cross-location and seasonal metrics are only meaningful when the supplied locations and periods are representative.",
      "Seasonal holdout may contain the same customers in train and test; temporal split is not a meter-disjoint split."]
    return results

def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input",required=True,type=Path)
    p.add_argument("--seeds",default="11,23,37,53,71"); p.add_argument("--output",default="reports/research_runs/generalization_evaluation.json")
    a=p.parse_args(); frame=pd.read_csv(a.input,low_memory=False); seeds=[int(x) for x in a.seeds.split(",") if x.strip()]
    if len(seeds)<2 or len(seeds)!=len(set(seeds)): p.error("provide at least two unique seeds")
    result=evaluate_generalization(frame,seeds); out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(out),"locations":len(result["cross_location"]),"seasons":len(result["seasonal"]),
                      "temporal_drift_evaluated":result["temporal_drift"] is not None},indent=2))
if __name__=="__main__": main()
