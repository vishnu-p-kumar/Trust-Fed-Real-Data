from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.federated.consumption_forecast import run_consumption_forecast


def _summary(values: list[float], *, nonnegative: bool = True) -> dict[str, object]:
    array = pd.Series(values, dtype=float)
    mean = float(array.mean())
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    critical = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(len(array), 1.96)
    half = critical * std / math.sqrt(len(array)) if len(array) > 1 else None
    lower = max(0.0, mean-half) if nonnegative else mean-half
    ci = [lower, mean+half] if half is not None else [None, None]
    return {"mean": mean, "std": std, "ci95_t": ci, "n": int(len(array))}


def _summarize_runs(runs: list[dict]) -> dict[str, object]:
    metrics: dict[str, object] = {}
    for split in ("validation", "test"):
        methods = sorted(runs[0]["metrics"][split])
        metrics[split] = {
            method: {
                key: _summary([float(run["metrics"][split][method][key]) for run in runs])
                for key in ("mae_kwh", "rmse_kwh", "wape")
            } for method in methods
        }
    paired_mae_delta = {
        method: _summary([
            float(run["metrics"]["test"][method]["mae_kwh"] - run["metrics"]["test"]["persistence"]["mae_kwh"])
            for run in runs
        ], nonnegative=False) for method in ("centralized", "fedavg", "trimmed_mean", "local_only")
    }
    return {"metrics": metrics, "test_mae_difference_vs_persistence": paired_mae_delta}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate meter-disjoint federated CEEW consumption forecasting.")
    parser.add_argument("--input", nargs="+", required=True, help="normalized CEEW CSV/CSV.GZ files")
    parser.add_argument("--interval", default="1D", help="source cadence, e.g. 1D or 3min")
    parser.add_argument("--client-partition", choices=["meter_groups", "location"], default="meter_groups",
                        help="random complete-meter groups or city-level non-IID clients")
    parser.add_argument("--clients", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--local-epochs", type=int, default=5)
    parser.add_argument("--learning-rate", type=float, default=.02)
    parser.add_argument("--learning-rate-candidates", nargs="+", type=float, default=None,
                        help="select using validation FedAvg MAE only")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--seeds", nargs="+", type=int, default=None,
                        help="repeat over meter-to-client assignment seeds; reports seed-sensitivity intervals")
    parser.add_argument("--max-rows-per-file", type=int, default=None,
                        help="optional memory-bounded smoke subset; results then cover only the selected rows")
    parser.add_argument("--output", default="reports/research_runs/ceew_forecast.json")
    args = parser.parse_args()
    frames = []
    for path in args.input:
        source = Path(path)
        if not source.is_file():
            parser.error(f"normalized input does not exist: {source}")
        if source.stat().st_size > 250_000_000 and args.max_rows_per_file is None:
            parser.error(f"large input requires --max-rows-per-file or daily aggregate input: {source.name}")
        frames.append(pd.read_csv(source, compression="infer", low_memory=False, nrows=args.max_rows_per_file))
    frame = pd.concat(frames, ignore_index=True)
    seeds = args.seeds if args.seeds is not None else [args.seed]
    if len(set(seeds)) != len(seeds):
        parser.error("seeds must be unique")
    runs = [run_consumption_forecast(frame, clients=args.clients, rounds=args.rounds,
                                     local_epochs=args.local_epochs, learning_rate=args.learning_rate,
                                     learning_rate_candidates=args.learning_rate_candidates,
                                     seed=seed, interval=args.interval,
                                     client_partition=args.client_partition) for seed in seeds]
    result = runs[0] if len(runs) == 1 else {
        "task": "CEEW unlabeled consumption forecast seed sensitivity study",
        "protocol": {"seeds": seeds,
                     "seed_variation": "meter-to-client assignment only; each run uses the same chronological per-meter split",
                     "intervals": "95% Student t intervals summarize client-allocation sensitivity, not population sampling uncertainty",
                     "hyperparameter_selection": "validation FedAvg MAE independently per seed; final test is not used for selection"},
        "summary": _summarize_runs(runs),
        "runs": runs,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    preview = ({"test_summary": result["summary"]["metrics"]["test"], "paired_mae_delta": result["summary"]["test_mae_difference_vs_persistence"]}
               if len(seeds) > 1 else {"counts": result["counts"], "test_metrics": result["metrics"]["test"],
                                       "anomaly_proxy": result["forecast_residual_anomaly_proxy"]})
    print(json.dumps({"output": str(output), **preview}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
