"""One-factor-at-a-time sensitivity study for HATTA/FL research parameters.

Uses generated synthetic data unless a caller separately extends the experiment
API with a labelled frame. Results are protocol diagnostics, not field accuracy.
"""
from __future__ import annotations
import argparse, json, math, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.federated.experiment import run_experiment

SWEEPS = {
    "malicious_fraction": ([0.10, 0.25, 0.40], {"attack": "scale"}),
    "trust_mad_multiplier": ([1.5, 2.5, 3.5], {"attack": "sign"}),
    "trim_fraction": ([0.05, 0.10, 0.20], {"attack": "none"}),
    "local_epochs": ([1, 2, 4], {"attack": "none"}),
    "client_participation": ([0.50, 0.75, 1.0], {"attack": "stale"}),
    "hatta_trust_weight": ([0.25, 0.50, 0.75], {"attack": "scale"}),
    "benign_shift_strength": ([0.0, 0.75, 1.5], {"attack": "none"}),
}
METHODS = ("fedavg", "fedavg_dp", "fedprox", "trimmed_mean", "multi_krum", "trust", "hatta", "centralized")
METRICS = ("accuracy", "precision", "recall", "f1", "pr_auc", "roc_auc", "false_positive_rate")

def stats(values):
    x=np.asarray(values,dtype=float)
    mean=float(x.mean()); std=float(x.std(ddof=1)) if len(x)>1 else 0.0
    half=1.96*std/math.sqrt(len(x)) if len(x)>1 else 0.0
    return {"mean":mean,"std":std,"ci95_normal_approx":[mean-half,mean+half],"n":len(x)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds",default="11,23,37")
    p.add_argument("--clients",type=int,default=6)
    p.add_argument("--rounds",type=int,default=3)
    p.add_argument("--samples",type=int,default=600)
    p.add_argument("--output",default="reports/research_runs/sensitivity_analysis.json")
    a=p.parse_args(); seeds=[int(v) for v in a.seeds.split(",") if v.strip()]
    if len(seeds)<2 or len(seeds)!=len(set(seeds)): p.error("provide at least two unique seeds")
    records=[]; started=time.perf_counter()
    for parameter,(values,scenario) in SWEEPS.items():
        for value in values:
            for seed in seeds:
                cfg={"seed":seed,"clients":a.clients,"rounds":a.rounds,"local_epochs":2,
                     "samples":a.samples,"partition":"severe","attack":scenario["attack"],
                     "malicious_fraction":0.25,"attack_intensity":3.0,"dp_enabled":True,
                     "dp_noise_multiplier":1.5,"trust_evidence":"utility",
                     parameter:value}
                if parameter=="malicious_fraction": cfg[parameter]=value
                if parameter=="benign_shift_strength": cfg["attack"]="none"; cfg[parameter]=value
                result=run_experiment(cfg)
                records.append({"parameter":parameter,"value":value,"seed":seed,
                    "metrics":{m:{k:result["metrics"][m][k] for k in METRICS}
                               for m in METHODS if m in result["metrics"]},
                    "security":{k:result["security"][k] for k in
                        ("detection_precision","detection_recall","honest_false_accusation_rate")},
                    "efficiency":result["efficiency"],"privacy":result["privacy"]})
    summary={}
    for parameter,(values,_) in SWEEPS.items():
        summary[parameter]={}
        for value in values:
            subset=[r for r in records if r["parameter"]==parameter and r["value"]==value]
            summary[parameter][str(value)]={"methods":{},"security":{},"efficiency":{}}
            for method in METHODS:
                if all(method in r["metrics"] for r in subset):
                    summary[parameter][str(value)]["methods"][method]={
                        metric:stats([r["metrics"][method][metric] for r in subset]) for metric in METRICS}
            for metric in ("detection_precision","detection_recall","honest_false_accusation_rate"):
                summary[parameter][str(value)]["security"][metric]=stats([r["security"][metric] for r in subset])
            for metric in ("training_seconds","communication_bytes","mean_participants_per_round"):
                summary[parameter][str(value)]["efficiency"][metric]=stats([r["efficiency"][metric] for r in subset])
    output={"protocol":"one-factor-at-a-time synthetic sensitivity study","seeds":seeds,
        "parameters":{k:v[0] for k,v in SWEEPS.items()},"records":records,"summary":summary,
        "elapsed_seconds":time.perf_counter()-started,
        "limitations":["Synthetic data only; no real-world theft detection claim.",
          "One-factor-at-a-time sweeps do not identify parameter interactions.",
          "Confidence intervals describe seed variability, not population uncertainty.",
          "Client participation is simulated by deterministic seeded sampling; network dropout is not emulated.",
          "DP-HATTA is not claimed because current private-update-derived trust weights are outside the DP guarantee."]}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(out),"runs":len(records),"parameters":len(SWEEPS),"seeds":len(seeds)},indent=2))
if __name__=="__main__": main()
