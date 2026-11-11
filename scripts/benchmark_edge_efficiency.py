"""Reproducible CPU-side edge proxy benchmark for prepared SGCC features.

This is a workstation benchmark, not a physical smart-meter deployment.
"""
from __future__ import annotations
import argparse, json, pickle, platform, time, tracemalloc
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"))
    p.add_argument("--rows",type=int,default=6000)
    p.add_argument("--output",type=Path,default=Path("reports/research_runs/edge_efficiency_benchmark.json"))
    a=p.parse_args()
    frame=pd.read_csv(a.input,low_memory=False)
    if len(frame)>a.rows:
        frame=pd.concat([g.sample(n=min(len(g),max(1,int(a.rows*len(g)/len(frame)))),random_state=77)
                         for _,g in frame.groupby("is_theft")],ignore_index=True)
    y=frame["is_theft"].astype(int)
    X=frame.drop(columns=["meter_id","is_theft"],errors="ignore").select_dtypes(include=[np.number,"bool"])
    X=X.replace([np.inf,-np.inf],np.nan)
    xtr,xte,ytr,yte=train_test_split(X,y,test_size=.2,random_state=77,stratify=y)
    models={
      "extra_trees":ExtraTreesClassifier(n_estimators=120,max_depth=16,min_samples_leaf=3,
          class_weight="balanced",n_jobs=2,random_state=77),
      "hist_gradient":HistGradientBoostingClassifier(max_iter=100,learning_rate=.05,
          max_leaf_nodes=15,random_state=77),
    }
    results={}
    for name,estimator in models.items():
        pipe=make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),estimator)
        start=time.perf_counter()
        if name=="hist_gradient":
            counts=np.bincount(ytr.to_numpy(),minlength=2)
            weights=np.where(ytr.to_numpy()==1,len(ytr)/(2*max(1,counts[1])),
                             len(ytr)/(2*max(1,counts[0])))
            pipe.fit(xtr,ytr,histgradientboostingclassifier__sample_weight=weights)
        else:
            pipe.fit(xtr,ytr)
        training=time.perf_counter()-start
        batch=xte.iloc[:min(512,len(xte))]
        tracemalloc.start()
        t0=time.perf_counter()
        for _ in range(10):
            pipe.predict_proba(batch)
        elapsed=time.perf_counter()-t0
        _,peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
        payload=pickle.dumps(pipe,protocol=pickle.HIGHEST_PROTOCOL)
        n=len(batch)*10
        results[name]={
          "training_seconds":training,"inference_batch_rows":len(batch),
          "inference_repeats":10,"mean_latency_ms_per_row":elapsed*1000/max(1,n),
          "peak_python_traced_memory_bytes":int(peak),"serialized_model_bytes":len(payload),
          "test_accuracy":float(pipe.score(xte,yte)),
        }
    output={"benchmark":"local CPU workstation edge proxy; not physical meter hardware",
      "python":platform.python_version(),"platform":platform.platform(),"cpu_count":__import__("os").cpu_count(),
      "rows":len(frame),"features":int(X.shape[1]),"results":results,
      "limitations":["Latency and memory depend on this execution environment.",
        "No physical smart-meter, embedded CPU, power draw or network link was measured.",
        "Accuracy is an internal holdout sanity check, not the primary SGCC benchmark."]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"results":results},indent=2))
if __name__=="__main__": main()
