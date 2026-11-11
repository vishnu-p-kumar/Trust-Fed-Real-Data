"""Run multi-seed FL robustness experiments and emit confidence summaries."""
from __future__ import annotations
import argparse, json, time
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from src.federated.experiment import run_experiment

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--seeds",default="11,23,37")
    p.add_argument("--clients",type=int,default=6)
    p.add_argument("--rounds",type=int,default=4)
    p.add_argument("--samples",type=int,default=900)
    p.add_argument("--output",default="reports/research_runs/robustness_suite.json")
    a=p.parse_args(); seeds=[int(x) for x in a.seeds.split(",") if x.strip()]
    scenarios=[("iid_benign","iid","none"),("non_iid_benign","severe","none"),
               ("non_iid_label_flip","severe","label_flip"),("non_iid_scale_attack","severe","scale"),
               ("non_iid_sign_attack","severe","sign"),
               ("non_iid_backdoor","severe","backdoor"),
               ("non_iid_gaussian","severe","gaussian"),
               ("non_iid_collusion","severe","collusion"),
               ("non_iid_model_replacement","severe","model_replacement"),
               ("non_iid_stale_update","severe","stale"),
               ("non_iid_low_slow","severe","low_slow"),
               ("non_iid_adaptive_mimic","severe","adaptive_mimic")]
    runs=[]
    for scenario,partition,attack in scenarios:
        for seed in seeds:
            start=time.perf_counter()
            result=run_experiment({"seed":seed,"clients":a.clients,"rounds":a.rounds,
              "local_epochs":2,"samples":a.samples,"partition":partition,"attack":attack,
              "malicious_fraction":0.25,"attack_intensity":4.0})
            metrics=result.get("metrics",{})
            selected={name:metrics.get(name,{}) for name in ("fedavg","fedprox","fedavg_dp","multi_krum","trust","hatta","trimmed_mean","centralized")}
            runs.append({"scenario":scenario,"seed":seed,"partition":partition,"attack":attack,
                         "elapsed_seconds":time.perf_counter()-start,"metrics":selected,
                         "security":result.get("security",{}),"recovery":result.get("recovery",{})})
    summary={}
    for scenario,_,_ in scenarios:
        subset=[r for r in runs if r["scenario"]==scenario]
        summary[scenario]={}
        for method in ("fedavg","fedprox","fedavg_dp","multi_krum","trust","hatta","trimmed_mean","centralized"):
            summary[scenario][method]={}
            metric_names=sorted({k for run in subset for k,v in run["metrics"].get(method,{}).items() if isinstance(v,(int,float))})
            for metric in metric_names:
                vals=[float(r["metrics"][method][metric]) for r in subset if metric in r["metrics"].get(method,{}) and np.isfinite(r["metrics"][method][metric])]
                if vals:
                    arr=np.asarray(vals); half=1.96*arr.std(ddof=1)/np.sqrt(len(arr)) if len(arr)>1 else 0
                    summary[scenario][method][metric]={"mean":float(arr.mean()),"std":float(arr.std(ddof=1)) if len(arr)>1 else 0.0,
                      "ci95":[float(arr.mean()-half),float(arr.mean()+half)],"n":len(arr)}
    output={"generated_at":time.time(),"seeds":seeds,"runs":runs,"summary":summary,
            "limitations":"Synthetic controlled benchmark; confidence intervals over selected seeds do not establish external validity."}
    path=Path(a.output); path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(output,indent=2,default=str))
    print(json.dumps({"output":str(path),"runs":len(runs),"scenarios":len(scenarios)},indent=2))
if __name__=="__main__": main()
