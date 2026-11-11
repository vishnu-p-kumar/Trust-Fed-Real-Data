"""Create a CEEW provenance/quality manifest from one or more raw CSVs."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.ceew_dataset import ingest_ceew_files

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",nargs="+",required=True,type=Path)
    p.add_argument("--output-dir",type=Path,default=Path("datasets/ceew/processed"))
    p.add_argument("--chunksize",type=int,default=100000)
    p.add_argument("--max-rows-per-file",type=int)
    p.add_argument("--write-normalized",action="store_true")
    a=p.parse_args()
    manifest=ingest_ceew_files(a.input,a.output_dir,chunksize=a.chunksize,
        max_rows_per_file=a.max_rows_per_file,write_normalized=a.write_normalized)
    print(json.dumps({"manifest":str(a.output_dir/"ceew_manifest.json"),
      "files":len(manifest["files"]),
      "rows":sum(x["row_count_processed"] for x in manifest["files"]),
      "meters_by_location":manifest["distinct_meter_count_by_location"],
      "complete_files":sum(bool(x["is_complete_source"]) for x in manifest["files"])},indent=2))
if __name__=="__main__": main()
