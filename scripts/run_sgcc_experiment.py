from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.federated.datasets import load_sgcc_csv
from src.federated.experiment import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(description="Train/evaluate the federated prototype on an authorized local SGCC CSV.")
    parser.add_argument("--csv", required=True, type=Path, help="local extracted wide-format SGCC CSV")
    parser.add_argument("--labels", type=Path, help="optional separate meter-ID/FLAG CSV")
    parser.add_argument("--expected-sha256", help="optional expected input file SHA-256")
    parser.add_argument("--output", type=Path, default=Path("reports/research_runs/sgcc"))
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--clients", type=int, default=8)
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--local-epochs", type=int, default=1)
    parser.add_argument("--partition", choices=("iid", "moderate", "severe"), default="severe")
    parser.add_argument("--attack", choices=("none", "sign", "scale", "label_flip", "slow"), default="none")
    parser.add_argument("--malicious-fraction", type=float, default=0.25)
    args = parser.parse_args()

    frame, provenance = load_sgcc_csv(args.csv, labels_path=args.labels,
                                      expected_sha256=args.expected_sha256,
                                      manifest_path=args.output / "dataset_provenance.json")
    result = run_experiment({"seed":args.seed,"clients":args.clients,"rounds":args.rounds,
        "local_epochs":args.local_epochs,"partition":args.partition,"attack":args.attack,
        "malicious_fraction":args.malicious_fraction}, dataframe=frame, output_dir=args.output)
    result["dataset_provenance"]={key:value for key,value in provenance.items() if key!="features"}
    (args.output / "results.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(args.output),"meters":provenance["meter_count"],
                      "features":provenance["feature_count"],"metrics":result["metrics"],
                      "split":result["split"]},indent=2))


if __name__ == "__main__":
    main()
