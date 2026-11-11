"""Gate multi-seed theft evaluation on explicit independent-label provenance.

A provenance JSON is an assertion supplied by the data owner, not cryptographic
proof. The evaluator verifies its required fields and file hash before training.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.evaluate_theft_models import evaluate

REQUIRED = ("label_source", "verification_method", "verified_by_organization", "verified_at", "adjudication_protocol")
def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""): h.update(chunk)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(description="Customer-disjoint multi-seed evaluation for independently verified theft labels")
    p.add_argument("--input",required=True,type=Path); p.add_argument("--provenance",required=True,type=Path)
    p.add_argument("--seeds",default="11,23,37,53,71"); p.add_argument("--output",default="reports/research_runs/verified_theft_evaluation.json")
    a=p.parse_args()
    if not a.input.is_file() or not a.provenance.is_file(): p.error("input CSV and provenance JSON must both exist")
    provenance=json.loads(a.provenance.read_text(encoding="utf-8"))
    missing=[k for k in REQUIRED if not str(provenance.get(k,"")).strip()]
    if missing: p.error(f"provenance missing required fields: {missing}")
    if provenance.get("label_source_type")!="independent_utility_inspection":
        p.error("refusing real-world claim: label_source_type must be independent_utility_inspection")
    digest=sha256(a.input)
    if provenance.get("dataset_sha256")!=digest: p.error("dataset_sha256 does not match the supplied CSV")
    frame=pd.read_csv(a.input,low_memory=False)
    seeds=[int(v.strip()) for v in a.seeds.split(",") if v.strip()]
    if len(seeds)<2 or len(seeds)!=len(set(seeds)): p.error("at least two unique seeds are required")
    runs=[evaluate(frame,seed) for seed in seeds]
    model_names=list(runs[0]["metrics"])
    summary={}
    for model in model_names:
        summary[model]={}
        for metric in ("precision","recall","f1","balanced_accuracy","roc_auc","average_precision"):
            vals=np.asarray([r["metrics"][model][metric] for r in runs],dtype=float)
            mean=float(vals.mean()); std=float(vals.std(ddof=1)); half=1.96*std/math.sqrt(len(vals))
            summary[model][metric]={"mean":mean,"std":std,"ci95_normal_approx":[mean-half,mean+half],"n":len(vals)}
    result={"evaluation_type":"independently-inspected theft-label claim; provenance self-attested by data owner",
      "dataset_sha256":digest,"provenance":provenance,"seeds":seeds,"runs":runs,"summary":summary,
      "limitations":["This tool checks provenance metadata and file integrity, not the truth of the inspection records.",
        "Independent utility audit and legal permission must be verified outside this software.",
        "Customer-disjoint holdouts do not replace temporal, geographic or external-utility validation."]}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(out),"dataset_sha256":digest,"seeds":len(seeds),"models":model_names},indent=2))
if __name__=="__main__": main()
