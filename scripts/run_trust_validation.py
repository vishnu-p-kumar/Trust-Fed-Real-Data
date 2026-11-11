from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.federated.experiment import run_calibrated_study


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the calibrated synthetic trust validation study.")
    parser.add_argument("--calibration-seeds", nargs="+", type=int, default=[42, 43, 44, 45, 46])
    parser.add_argument("--evaluation-seeds", nargs="+", type=int, default=[52, 53, 54, 55, 56])
    parser.add_argument("--output", type=Path,
                        default=Path("reports/research_runs/trust_validation_20261028.json"))
    parser.add_argument("--samples", type=int, default=400)
    parser.add_argument("--features", type=int, default=10)
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--local-epochs", type=int, default=2)
    args = parser.parse_args()

    result = run_calibrated_study(
        calibration_seeds=args.calibration_seeds,
        evaluation_seeds=args.evaluation_seeds,
        config={
            "samples": args.samples,
            "features": args.features,
            "clients": args.clients,
            "rounds": args.rounds,
            "local_epochs": args.local_epochs,
            "partition": "severe",
            "attack_intensity": 4.0,
            "max_update_norm": 5.0,
            "trim_fraction": 0.1,
        },
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output),
                      "threshold_protocol": result["threshold_protocol"],
                      "primary_evidence": result["primary_evidence"],
                      "calibration_scenario_count": len(result["calibration"]["utility"])}, indent=2))


if __name__ == "__main__":
    main()
