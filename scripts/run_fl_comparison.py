"""Reproducible multi-seed FL baseline and trust-evidence ablation benchmark.

The generated data are synthetic. This runner is for software/research protocol
validation, not for claiming field performance on utility theft labels.
"""
from __future__ import annotations
import argparse, json, math, sys, time
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.federated.experiment import run_experiment

METHODS = ("centralized", "fedavg", "fedavg_dp", "fedprox", "trimmed_mean", "multi_krum", "trust", "hatta")
METRICS = ("accuracy", "precision", "recall", "f1", "macro_f1", "pr_auc", "roc_auc", "false_positive_rate")
ABLATIONS = ("utility", "utility_integrity", "utility_integrity_temporal", "utility_heterogeneity")

def summarize(values):
    x=np.asarray(values,dtype=float)
    if not len(x) or not np.isfinite(x).all():
        raise ValueError("cannot summarize empty/non-finite values")
    mean=float(x.mean()); std=float(x.std(ddof=1)) if len(x)>1 else 0.0
    # Normal-approximation interval; clearly report n and do not imply population-level certainty.
    half=1.96*std/math.sqrt(len(x)) if len(x)>1 else 0.0
    return {"mean":mean,"std":std,"ci95_normal_approx":[mean-half,mean+half],"n":int(len(x))}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",default="11,23,37,53,71")
    p.add_argument("--clients",type=int,default=8)
    p.add_argument("--rounds",type=int,default=5)
    p.add_argument("--samples",type=int,default=1200)
    p.add_argument("--output",default="reports/research_runs/fl_comparison.json")
    p.add_argument("--include-attacks",action="store_true")
    a=p.parse_args(); seeds=[int(v.strip()) for v in a.seeds.split(",") if v.strip()]
    if len(seeds)<2 or len(seeds)!=len(set(seeds)):
        p.error("provide at least two unique seeds")
    scenarios=[{"name":"iid_benign","partition":"iid","attack":"none"},
               {"name":"non_iid_benign","partition":"severe","attack":"none"}]
    if a.include_attacks:
        scenarios += [{"name":f"non_iid_{attack}","partition":"severe","attack":attack,
                       "malicious_fraction":0.25,"attack_intensity":3.0}
                      for attack in ("label_flip","scale","sign","backdoor","gaussian","collusion","model_replacement","stale")]
    records=[]; started=time.perf_counter()
    for scenario in scenarios:
        for ablation in ABLATIONS:
            for seed in seeds:
                cfg={"seed":seed,"clients":a.clients,"rounds":a.rounds,"local_epochs":2,
                     "samples":a.samples,"features":12,"learning_rate":0.10,
                     "partition":scenario["partition"],"attack":scenario["attack"],
                     "malicious_fraction":scenario.get("malicious_fraction",0.0),
                     "attack_intensity":scenario.get("attack_intensity",3.0),
                     "trust_evidence":ablation,"dp_enabled":True,"dp_noise_multiplier":1.5,"dp_clip_norm":5.0}
                result=run_experiment(cfg)
                records.append({"scenario":scenario["name"],"ablation":ablation,"seed":seed,
                    "metrics":{m:{k:result["metrics"][m][k] for k in METRICS} for m in METHODS if m in result["metrics"]},
                    "local_only":result["metrics"].get("local_only",{}),
                    "privacy":result.get("privacy",{}),
                    "security":{k:result["security"].get(k) for k in
                                ("detection_precision","detection_recall","honest_false_accusation_rate")},
                    "efficiency":result["efficiency"],"split":result["split"]})
    summary={}
    for scenario in scenarios:
        name=scenario["name"]; summary[name]={}
        for ablation in ABLATIONS:
            subset=[r for r in records if r["scenario"]==name and r["ablation"]==ablation]
            summary[name][ablation]={"methods":{},"detection":{},"local_only":{}}
            for method in METHODS:
                if all(method in r["metrics"] for r in subset):
                    summary[name][ablation]["methods"][method]={metric:summarize([r["metrics"][method][metric] for r in subset]) for metric in METRICS}
            local_metrics=sorted({metric for record in subset for client in record["local_only"].values()
                                  for metric,value in client.items() if isinstance(value,(int,float))})
            for metric in local_metrics:
                summary[name][ablation]["local_only"][metric]=summarize([
                    float(client[metric]) for record in subset for client in record["local_only"].values()
                    if metric in client and isinstance(client[metric],(int,float))])
            for metric in ("detection_precision","detection_recall","honest_false_accusation_rate"):
                summary[name][ablation]["detection"][metric]=summarize([r["security"][metric] for r in subset])
    output={"protocol":"synthetic multi-seed federated baseline comparison",
      "seeds":seeds,"scenarios":scenarios,"methods":METHODS,"trust_evidence_ablations":ABLATIONS,
      "records":records,"summary":summary,"elapsed_seconds":time.perf_counter()-started,
      "limitations":["Synthetic data only; not real-world theft evaluation.",
        "Normal-approximation confidence intervals are descriptive and seed counts are modest.",
        "FedProx is a local optimization baseline; it is not a separate secure aggregation protocol.",
        "Multi-Krum Byzantine bound is set from simulated malicious fraction and assumes its threat model.",
        "DP-FedAvg uses the experiment's configured client-update Gaussian mechanism and conservative full-participation RDP accounting.",
        "DP-HATTA is intentionally not reported: trust weights depend on private update validation evidence, so the current DP guarantee does not cover the data-dependent trust mechanism."]}
    path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(path),"runs":len(records),"scenarios":len(scenarios),"seeds":len(seeds)},indent=2))
if __name__=="__main__": main()
