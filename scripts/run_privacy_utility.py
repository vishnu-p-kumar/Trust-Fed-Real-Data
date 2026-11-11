"""Evaluate client-level Gaussian DP-FedAvg privacy/utility trade-offs.

The accountant uses full-participation RDP composition without subsampling
amplification. This does not certify privacy for the whole application.
"""
from __future__ import annotations
import argparse, json, math, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.federated.experiment import run_experiment

NOISE_MULTIPLIERS=(0.5,0.75,1.0,1.5,2.0,3.0)
METRICS=("accuracy","precision","recall","f1","pr_auc","roc_auc","false_positive_rate")
def summary(values):
    a=np.asarray(values,dtype=float); mean=float(a.mean()); sd=float(a.std(ddof=1)) if len(a)>1 else 0.0
    h=1.96*sd/math.sqrt(len(a)) if len(a)>1 else 0.0
    return {"mean":mean,"std":sd,"ci95_normal_approx":[mean-h,mean+h],"n":len(a)}
def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--seeds",default="11,23,37,53,71")
    p.add_argument("--clients",type=int,default=8); p.add_argument("--rounds",type=int,default=5)
    p.add_argument("--samples",type=int,default=1200); p.add_argument("--partition",choices=["iid","moderate","severe"],default="severe")
    p.add_argument("--output",default="reports/research_runs/privacy_utility_curve.json")
    a=p.parse_args(); seeds=[int(x) for x in a.seeds.split(",") if x.strip()]
    if len(seeds)<2 or len(seeds)!=len(set(seeds)): p.error("at least two unique seeds are required")
    records=[]; trust_records=[]; started=time.perf_counter()
    for noise in NOISE_MULTIPLIERS:
        for seed in seeds:
            result=run_experiment({"seed":seed,"clients":a.clients,"rounds":a.rounds,"local_epochs":2,
                "samples":a.samples,"partition":a.partition,"attack":"none","dp_enabled":True,
                "dp_noise_multiplier":noise,"dp_clip_norm":5.0,"dp_delta":1e-5})
            records.append({"noise_multiplier":noise,"seed":seed,
                "fedavg":{k:result["metrics"]["fedavg"][k] for k in METRICS},
                "dp_fedavg":{k:result["metrics"]["fedavg_dp"][k] for k in METRICS},
                "privacy":result["privacy"]})
            trust_result=run_experiment({"seed":seed,"clients":a.clients,"rounds":a.rounds,"local_epochs":2,
                "samples":a.samples,"partition":a.partition,"attack":"none","trust_dp_enabled":True,
                "trust_dp_noise_multiplier":noise,"dp_delta":1e-5})
            trust_records.append({"noise_multiplier":noise,"seed":seed,
                "hatta":{k:trust_result["metrics"]["hatta"][k] for k in METRICS},
                "trust_privacy":trust_result["trust_privacy"]})
    curve={}
    for noise in NOISE_MULTIPLIERS:
        subset=[r for r in records if r["noise_multiplier"]==noise]
        curve[str(noise)]={"epsilon":summary([r["privacy"]["epsilon"] for r in subset]),
            "fedavg":{m:summary([r["fedavg"][m] for r in subset]) for m in METRICS},
            "dp_fedavg":{m:summary([r["dp_fedavg"][m] for r in subset]) for m in METRICS}}
    trust_curve={}
    for noise in NOISE_MULTIPLIERS:
        subset=[r for r in trust_records if r["noise_multiplier"]==noise]
        trust_curve[str(noise)]={"epsilon":summary([r["trust_privacy"]["epsilon"] for r in subset]),
            "hatta":{m:summary([r["hatta"][m] for r in subset]) for m in METRICS}}
    output={"protocol":"client-level Gaussian DP-FedAvg and separately scoped DP trust-evidence utility curves",
        "protected_unit":"one participating client update per round",
        "adjacency":"replacement adjacency for clipped client updates",
        "accounting":"full-participation Gaussian RDP composition; no subsampling amplification",
        "rounds":a.rounds,"delta":1e-5,"seeds":seeds,"noise_multipliers":list(NOISE_MULTIPLIERS),
        "records":records,"curve":curve,"trust_evidence_records":trust_records,
        "trust_evidence_curve":trust_curve,"elapsed_seconds":time.perf_counter()-started,
        "limitations":["Synthetic data only; utility results are not real theft-detection performance.",
          "The guarantee covers the configured noisy client-update release, not logs, checkpoints, dashboard exports, raw data, or every API output.",
          "No end-to-end DP-HATTA guarantee is claimed. The separate trust-evidence mechanism noises a bounded utility/integrity/temporal vector only; raw updates and validation-derived harms remain visible to the coordinator.",
          "Validate the adjacency, clipping, sampling and release assumptions for the deployed protocol."]}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(out),"runs":len(records),"trust_evidence_runs":len(trust_records),"noise_multipliers":len(NOISE_MULTIPLIERS),"seeds":len(seeds)},indent=2))
if __name__=="__main__": main()
