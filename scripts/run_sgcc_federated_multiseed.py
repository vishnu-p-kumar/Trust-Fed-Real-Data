"""Run the federated algorithm comparison on real SGCC-labelled customer data."""
from __future__ import annotations
import argparse, json, math, sys
from pathlib import Path
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.federated.datasets import load_sgcc_csv
from src.federated.experiment import run_experiment

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--csv",type=Path,default=Path("datasets/sgcc/raw/sgcc_data.csv"))
    p.add_argument("--seeds",default="11,23,37")
    p.add_argument("--clients",type=int,default=4)
    p.add_argument("--rounds",type=int,default=2)
    p.add_argument("--local-epochs",type=int,default=1)
    p.add_argument("--partition",choices=["iid","moderate","severe"],default="severe")
    p.add_argument("--output",type=Path,default=Path("reports/research_runs/sgcc_federated_multiseed.json"))
    a=p.parse_args()
    seeds=[int(x.strip()) for x in a.seeds.split(",") if x.strip()]
    if len(seeds)<2 or len(set(seeds))!=len(seeds): p.error("provide at least two unique seeds")
    frame,provenance=load_sgcc_csv(a.csv)
    runs=[]
    for seed in seeds:
        runs.append(run_experiment({"seed":seed,"clients":a.clients,"rounds":a.rounds,
            "local_epochs":a.local_epochs,"partition":a.partition,"attack":"none",
            "malicious_fraction":0.0},dataframe=frame))
    methods=["centralized","fedavg","fedprox","trimmed_mean","multi_krum","trust","hatta"]
    metrics=["accuracy","precision","recall","f1","pr_auc","roc_auc","false_positive_rate"]
    summary={}
    for method in methods:
        summary[method]={}
        for metric in metrics:
            values=np.asarray([r["metrics"][method][metric] for r in runs],dtype=float)
            mean=float(values.mean()); std=float(values.std(ddof=1))
            tc={2:12.706,3:4.303,4:3.182,5:2.776,6:2.571,7:2.447,8:2.365,9:2.306}.get(len(values)-1,1.96)
            half=tc*std/math.sqrt(len(values))
            summary[method][metric]={"mean":mean,"std":std,"ci95_t":[max(0,mean-half),min(1,mean+half)] if metric!="false_positive_rate" else [max(0,mean-half),min(1,mean+half)],"n":len(values)}
    result={"dataset_provenance":{k:v for k,v in provenance.items() if k!="features"},
      "config":{"seeds":seeds,"clients":a.clients,"rounds":a.rounds,"local_epochs":a.local_epochs,
                "partition":a.partition,"attack":"none"},
      "protocol":"federated logistic-regression experiment; customer-disjoint train/validation/test; imputer and scaler fitted on training customers; results exploratory due to 2 communication rounds",
      "runs":runs,"summary":summary,
      "limitations":["SGCC is historical China utility data, not a live feed or Indian utility evaluation.",
        "This small-round federated experiment is a pilot; increase rounds and seeds for publication-grade comparison.",
        "The uploaded dataset contains benchmark FLAG labels but no individual inspection records."]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"seeds":len(seeds),"meters":provenance["meter_count"],
        "summary":{m:{k:round(v["mean"],4) for k,v in summary[m].items()} for m in methods}},indent=2))
if __name__=="__main__": main()
