from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from utils.helpers import ensure_project_dirs, generation_config


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Trust-Fed-Grid-X: SGCC-trained theft detection with live meter telemetry.")
    parser.add_argument("--start-api", action="store_true", help="Start the FastAPI server after model preparation.")
    parser.add_argument("--skip-training", action="store_true", help="Use existing model artifacts without retraining.")
    parser.add_argument("--demo-synthetic", action="store_true", help="Explicitly generate synthetic data and use the legacy synthetic demonstration pipeline.")
    parser.add_argument("--full-scale", action="store_true", help="Use the full synthetic demo configuration (demo mode only).")
    parser.add_argument("--num-meters", type=int, default=None, help="Override synthetic demo meter count.")
    parser.add_argument("--days", type=int, default=None, help="Override synthetic demo duration.")
    parser.add_argument("--forecast-epochs", type=int, default=5, help="Forecast-model epochs for synthetic demo mode.")
    parser.add_argument("--optimize-models", action="store_true", help="Run optional hyperparameter optimisation in synthetic demo mode.")
    parser.add_argument("--optimization-trials", type=int, default=8)
    parser.add_argument("--sgcc-target-recall", type=float, default=0.40, help="Validation recall target for SGCC live classifier threshold selection.")
    parser.add_argument("--sgcc-windows-per-customer", type=int, default=1, help="SGCC 30-day windows sampled per customer (1 is memory-efficient).")
    return parser.parse_args()


def load_local_env() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


def run_synthetic_demo(args: argparse.Namespace) -> None:
    from src.data_generator import generate_smart_meter_data
    from src.energy_efficiency import calculate_efficiency_metrics
    from src.model_optimizer import optimize_detection_models
    from src.preprocess import limit_theft_alerts, load_dataset
    from src.report_generator import generate_daily_report
    from src.risk_scoring import score_meter_risk
    from src.sample_outputs import export_sample_outputs
    from src.spatial_analysis import build_theft_heatmap
    from src.theft_detector import classify_meter_events
    from src.train_models import train_all_models

    paths = ensure_project_dirs()
    config = generation_config(full_scale=args.full_scale)
    if args.num_meters is not None:
        config["num_meters"] = args.num_meters
    if args.days is not None:
        config["days"] = args.days
    print("[DEMO ONLY] Generating synthetic smart-meter data...")
    sample_df = generate_smart_meter_data(**config)
    print(f"Synthetic demonstration dataset ready: {len(sample_df):,} rows")
    if args.optimize_models:
        print("Optimizing demonstration models...")
        print(optimize_detection_models(sample_df, trials=args.optimization_trials))
    if not args.skip_training:
        summary = train_all_models(dataset_path=paths.data_processed / "smart_meter_sample.csv",
                                   max_rows=config["sample_rows"], forecast_epochs=args.forecast_epochs)
        print("Synthetic demonstration training summary:", summary["classification"])
        live_frame = load_dataset(paths.live_dataset)
        predicted = calculate_efficiency_metrics(score_meter_risk(limit_theft_alerts(classify_meter_events(live_frame), max_alerts=2)))
        export_sample_outputs(predicted, forecast=summary.get("forecasting", {}))
        generate_daily_report(predicted, forecast=summary.get("forecasting", {}))
        build_theft_heatmap(predicted)


def main() -> None:
    load_local_env()
    args = parse_args()
    paths = ensure_project_dirs()
    if args.demo_synthetic:
        os.environ["SMARTGRID_DEMO_MODE"] = "1"
        run_synthetic_demo(args)
    else:
        os.environ["SMARTGRID_DEMO_MODE"] = "0"
        model_path = paths.model_dir / "sgcc_live_theft_model.pkl"
        metadata_path = paths.model_dir / "sgcc_live_theft_metadata.json"
        raw_sgcc = paths.root / "datasets" / "sgcc" / "raw" / "sgcc_data.csv"
        if not args.skip_training:
            if not raw_sgcc.exists():
                raise FileNotFoundError(f"SGCC raw dataset not found: {raw_sgcc}")
            ceew_sources = [
                paths.root / "datasets" / "ceew" / "raw" / "SM Cleaned Data MH Aggregated.csv",
                paths.root / "datasets" / "ceew" / "raw" / "SM Cleaned Data BR Aggregated.csv",
            ]
            if not all(path.exists() for path in ceew_sources):
                raise FileNotFoundError("CEEW Mathura/Bareilly daily aggregate sources are required for the default forecasting model.")
            # Keep the large SGCC feature/training allocation out of the process
            # that builds the CEEW forecaster. Separate processes release native
            # NumPy/pandas/sklearn allocations before the next dataset is loaded.
            sgcc_command = [
                sys.executable, str(paths.root / "scripts" / "train_sgcc_live_model.py"),
                "--input", str(raw_sgcc), "--model", str(model_path), "--metadata", str(metadata_path),
                "--target-recall", str(args.sgcc_target_recall),
                "--windows-per-customer", str(args.sgcc_windows_per_customer),
            ]
            subprocess.run(sgcc_command, cwd=paths.root, check=True)
            ceew_command = [
                sys.executable, str(paths.root / "scripts" / "train_ceew_forecaster.py"),
                "--mathura", str(ceew_sources[0]), "--bareilly", str(ceew_sources[1]),
                "--model", str(paths.model_dir / "ceew_consumption_forecaster.pkl"),
                "--metadata", str(paths.model_dir / "ceew_consumption_forecaster_metadata.json"),
            ]
            subprocess.run(ceew_command, cwd=paths.root, check=True)
        elif (
            not model_path.exists() or not metadata_path.exists()
            or not (paths.model_dir / "ceew_consumption_forecaster.pkl").exists()
            or not (paths.model_dir / "ceew_consumption_forecaster_metadata.json").exists()
        ):
            raise FileNotFoundError("--skip-training was requested, but the SGCC theft model or CEEW forecaster artifacts are missing. Remove --skip-training or run the relevant training scripts.")
        print("Runtime mode: LIVE TELEMETRY (synthetic model training is disabled).")
    if args.start_api:
        import uvicorn
        print("Starting Trust-Fed-Grid-X API on http://127.0.0.1:8000 ...")
        sender_process = None
        sender_log = None
        if not args.demo_synthetic and os.getenv("SMARTGRID_SYNTHETIC_LIVE_METERS", "0") == "1":
            sender_log = (paths.root / "synthetic_meter_sender.log").open("a", encoding="utf-8")
            sender_command = [
                sys.executable, str(paths.root / "scripts" / "synthetic_live_meter_sender.py"),
                "--count", os.getenv("SMARTGRID_SYNTHETIC_METER_COUNT", "800"),
                "--interval-seconds", os.getenv("SMARTGRID_SYNTHETIC_METER_INTERVAL_SECONDS", "300"),
                "--backfill-days", os.getenv("SMARTGRID_SYNTHETIC_METER_BACKFILL_DAYS", "30"),
            ]
            sender_process = subprocess.Popen(
                sender_command,
                cwd=paths.root,
                stdout=sender_log,
                stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            print("Synthetic live telemetry enabled: 800 meters, five-minute cadence.")
        try:
            uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)
        finally:
            if sender_process is not None:
                if sender_process.poll() is None:
                    sender_process.terminate()
                    try:
                        sender_process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        sender_process.kill()
                        sender_process.wait(timeout=5)
                if sender_log is not None:
                    sender_log.close()


if __name__ == "__main__":
    main()
