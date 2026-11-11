"""Run controlled adversarial federated pilots on SGCC-labelled customer features.

Attacks are simulated on selected federated clients; they are not observed utility attacks.
"""
from __future__ import annotations
import argparse, json, sys, time
from pathlib import Path
import numpy as np
import pandas as pd
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.federated.experiment import run_experiment

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"))
    parser.add_argument("--seeds", default="11,23,37")
    parser.add_argument("--clients", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--max-customers", type=int, default=5000,
                        help="stratified customer sample size for tractable adversarial runs; 0 uses all customers")
    parser.add_argument("--output", type=Path,
                        default=Path("reports/research_runs/sgcc_adversarial_suite.json"))
    args = parser.parse_args()
    seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
    if len(seeds) < 2 or len(seeds) != len(set(seeds)):
        parser.error("provide at least two unique evaluation seeds")
    if not args.input.is_file():
        parser.error(f"prepared SGCC feature file not found: {args.input}")
    frame = pd.read_csv(args.input, low_memory=False)
    if "meter_id" not in frame or "is_theft" not in frame:
        parser.error("prepared SGCC features must contain meter_id and is_theft")
    if frame["meter_id"].duplicated().any():
        parser.error("expected exactly one feature row per unique meter")
    if args.max_customers and len(frame) > args.max_customers:
        # Stratified by the published customer label, with a fixed seed. This is a
        # disclosed computational pilot, not a replacement for full-cohort testing.
        sampled = []
        for label, group in frame.groupby("is_theft"):
            count = max(1, int(round(args.max_customers * len(group) / len(frame))))
            sampled.append(group.sample(n=min(len(group), count), random_state=2026))
        frame = pd.concat(sampled, ignore_index=True).sample(frac=1, random_state=2026).reset_index(drop=True)
    provenance = {
        "dataset": "SGCC labelled customer-level engineered feature table",
        "feature_file": str(args.input),
        "meter_count": int(frame["meter_id"].nunique()),
        "feature_count": int(len([c for c in frame.select_dtypes(include=[np.number]).columns
                                  if c != "is_theft"])),
        "label_counts": {str(k): int(v) for k, v in frame["is_theft"].value_counts().to_dict().items()},
    }
    scenarios = [
        {"name": "benign", "attack": "none", "malicious_fraction": 0.0},
        {"name": "label_flip_25pct", "attack": "label_flip", "malicious_fraction": 0.25},
        {"name": "sign_flip_25pct", "attack": "sign", "malicious_fraction": 0.25},
        {"name": "collusion_25pct", "attack": "collusion", "malicious_fraction": 0.25},
        {"name": "gaussian_25pct", "attack": "gaussian", "malicious_fraction": 0.25,
         "attack_intensity": 1.5},
        {"name": "low_slow_25pct", "attack": "low_slow", "malicious_fraction": 0.25},
        {"name": "adaptive_mimic_25pct", "attack": "adaptive_mimic", "malicious_fraction": 0.25},
    ]
    records = []
    started = time.perf_counter()
    for scenario in scenarios:
        for seed in seeds:
            config = {
                "seed": seed, "clients": args.clients, "rounds": args.rounds,
                "local_epochs": 1, "batch_size": 1024, "partition": "severe",
                **scenario,
            }
            result = run_experiment(config, dataframe=frame)
            records.append({
                "scenario": scenario["name"], "seed": seed, "config": config,
                "metrics": {method: {key: result["metrics"][method][key]
                    for key in ("accuracy", "precision", "recall", "f1", "pr_auc",
                                "false_positive_rate")}
                    for method in ("centralized", "fedavg", "trimmed_mean",
                                   "multi_krum", "trust", "hatta")},
                "security": result["security"],
                "efficiency": result["efficiency"],
                "split": result["split"],
            })
    summary = {}
    for scenario in scenarios:
        name = scenario["name"]
        subset = [row for row in records if row["scenario"] == name]
        summary[name] = {}
        for method in ("centralized", "fedavg", "trimmed_mean", "multi_krum", "trust", "hatta"):
            summary[name][method] = {}
            for metric in ("accuracy", "precision", "recall", "f1", "pr_auc",
                           "false_positive_rate"):
                values = np.asarray([row["metrics"][method][metric] for row in subset], dtype=float)
                mean = float(values.mean())
                std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
                half = 4.303 * std / np.sqrt(len(values)) if len(values) == 3 else (
                    1.96 * std / np.sqrt(len(values)) if len(values) > 1 else 0.0)
                summary[name][method][metric] = {
                    "mean": mean, "std": std, "ci95_approx": [mean-half, mean+half],
                    "n": int(len(values)),
                }
        summary[name]["client_detection"] = {
            key: float(np.mean([row["security"][field] for row in subset]))
            for key, field in (("precision", "detection_precision"),
                               ("recall", "detection_recall"),
                               ("honest_false_accusation_rate", "honest_false_accusation_rate"))
        }
    output = {
        "dataset": "SGCC-labelled customer-level features",
        "dataset_provenance": {key: value for key, value in provenance.items() if key != "features"},
        "protocol": "stratified customer subset when max_customers is nonzero; customer-disjoint train/validation/test; severe label-skewed client partition; simulated malicious clients; attacks are not observed utility incidents",
        "seeds": seeds, "clients": args.clients, "rounds": args.rounds,
        "elapsed_seconds": time.perf_counter() - started,
        "records": records, "summary": summary,
        "limitations": [
            "Historical Chinese SGCC benchmark, not Indian utility validation.",
            "If max_customers is nonzero, this is a stratified customer subset; the reported customer count must accompany every result.",
            "Attacks are simulated in the federated training loop.",
            "Only the configured seeds, client count and rounds are evaluated; results are exploratory.",
            "The coordinator uses a training-only validation partition for trust evidence; this is not a privacy-preserving validation protocol.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "runs": len(records),
                      "scenarios": len(scenarios), "meters": provenance["meter_count"],
                      "elapsed_seconds": output["elapsed_seconds"]}, indent=2))

if __name__ == "__main__":
    main()
