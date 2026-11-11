"""One-command CEEW ingest -> provenance manifest -> meter-disjoint forecast pipeline."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.ceew_dataset import ingest_ceew_files
from src.federated.consumption_forecast import run_consumption_forecast

def main():
    p=argparse.ArgumentParser(description="Normalize raw CEEW smart-meter files and run unlabeled consumption forecasting")
    p.add_argument("--input",nargs="+",required=True); p.add_argument("--output-dir",default="data/processed/ceew")
    p.add_argument("--mode",choices=["auto","high_frequency","daily_aggregate"],default="auto")
    p.add_argument("--chunksize",type=int,default=100000); p.add_argument("--clients",type=int,default=4)
    p.add_argument("--rounds",type=int,default=3); p.add_argument("--local-epochs",type=int,default=5)
    p.add_argument("--interval",default="3min"); p.add_argument("--seeds",nargs="+",type=int,default=[11,23,37,53,71])
    p.add_argument("--client-partition",choices=["meter_groups","location"],default="meter_groups")
    p.add_argument("--max-rows-per-file",type=int,default=None); p.add_argument("--output",default="reports/research_runs/ceew_pipeline.json")
    a=p.parse_args()
    manifest=ingest_ceew_files(a.input,a.output_dir,mode=a.mode,chunksize=a.chunksize,
        max_rows_per_file=a.max_rows_per_file,write_normalized=True)
    paths=[Path(a.output_dir)/f["output_file"] for f in manifest["files"] if f.get("output_file")]
    if not paths: p.error("ingestion produced no normalized files")
    frames=[pd.read_csv(path,compression="infer",low_memory=False) for path in paths]
    frame=pd.concat(frames,ignore_index=True)
    runs=[run_consumption_forecast(frame,clients=a.clients,rounds=a.rounds,local_epochs=a.local_epochs,
        seed=seed,interval=a.interval,client_partition=a.client_partition) for seed in a.seeds]
    result={"task":"CEEW unlabeled consumption forecasting; not theft classification",
      "ingestion_manifest":str(Path(a.output_dir)/"ceew_manifest.json"),"ingestion":manifest,
      "forecast_protocol":{"seeds":a.seeds,"seed_variation":"client assignment seed",
        "split":"per-meter chronological train/validation/test","client_partition":a.client_partition},
      "runs":runs,"limitations":["CEEW readings do not provide verified theft ground-truth labels.",
        "This pipeline evaluates consumption forecasting and residual anomaly proxies only.",
        "Large datasets may require a machine with sufficient RAM for the forecasting stage."]}
    out=Path(a.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(out),"normalized_files":len(paths),"forecast_runs":len(runs),
      "label_status":"no verified theft labels in CEEW consumption data"},indent=2))
if __name__=="__main__": main()
