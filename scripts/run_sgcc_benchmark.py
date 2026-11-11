"""Multi-seed, customer-disjoint benchmark on prepared SGCC customer features."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.evaluate_theft_models import evaluate

def sha256(path):
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"))
    p.add_argument("--seeds",default="11,23,37,53,71")
    p.add_argument("--output",type=Path,default=Path("reports/research_runs/sgcc_customer_disjoint_benchmark.json"))
    a=p.parse_args()
    if not a.input.exists(): p.error(f"feature dataset not found: {a.input}")
    seeds=[int(x.strip()) for x in a.seeds.split(",") if x.strip()]
    if len(seeds)<2 or len(set(seeds))!=len(seeds): p.error("provide at least two unique seeds")
    frame=pd.read_csv(a.input,low_memory=False)
    if frame["meter_id"].nunique()!=len(frame): p.error("expected one feature row per unique meter")
    runs=[evaluate(frame,seed) for seed in seeds]
    models=list(runs[0]["metrics"])
    metrics=("precision","recall","f1","balanced_accuracy","roc_auc","average_precision","accuracy","false_positive_rate","mcc")
    summary={}
    for model in models:
        summary[model]={}
        for metric in metrics:
            vals=np.asarray([r["metrics"][model][metric] for r in runs],dtype=float)
            mean=float(vals.mean()); std=float(vals.std(ddof=1))
            # Student-t critical values for the small seed count.
            tcrit={2:12.706,3:4.303,4:3.182,5:2.776,6:2.571,7:2.447,8:2.365,9:2.306,10:2.262}.get(len(vals)-1,1.96)
            half=tcrit*std/math.sqrt(len(vals))
            lo,hi=mean-half,mean+half
            if metric not in ("mcc",): lo=max(0.0,lo); hi=min(1.0,hi)
            else: lo=max(-1.0,lo); hi=min(1.0,hi)
            summary[model][metric]={"mean":mean,"std":std,"ci95_t":[lo,hi],"n":len(vals)}
    result={
      "dataset":"SGCC Electricity Theft Detection benchmark",
      "source_file_sha256":None,
      "feature_file":str(a.input),"feature_sha256":sha256(a.input),
      "seeds":seeds,"runs":runs,"summary":summary,
      "protocol":"5 independent seeds; 80/20 customer-disjoint holdout; one row per customer; threshold=0.5 fixed; imputation and scaling fitted on training partition only",
      "label_definition":"FLAG=1 published theft/abnormal label; FLAG=0 normal label as documented in SGCC benchmark literature",
      "limitations":["This is a historical China utility benchmark, not a live stream or Indian utility sample.",
        "The upload includes the benchmark label but no customer-level inspection records; claims should be phrased as performance on SGCC-labelled data.",
        "No explicit dataset redistribution licence was found in the included README; raw data is included only as user-provided research input and should be redistributed only after checking applicable terms.",
        "This is a supervised centralized benchmark, not a federated comparison; use run_sgcc_experiment.py separately for federated experiments."]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"rows":len(frame),"seeds":len(seeds),"models":models,
      "summary":{m:{k:round(v["mean"],4) for k,v in summary[m].items()} for m in models}},indent=2))
if __name__=="__main__": main()
