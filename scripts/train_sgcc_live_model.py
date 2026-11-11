from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.sgcc_live_model import train_sgcc_live_model

def main() -> None:
    parser = argparse.ArgumentParser(description="Train the live 30-day electricity-theft classifier on SGCC only.")
    parser.add_argument("--input", type=Path, default=ROOT / "datasets/sgcc/raw/sgcc_data.csv")
    parser.add_argument("--model", type=Path, default=ROOT / "models/sgcc_live_theft_model.pkl")
    parser.add_argument("--metadata", type=Path, default=ROOT / "models/sgcc_live_theft_metadata.json")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--target-recall", type=float, default=0.40)
    parser.add_argument("--windows-per-customer", type=int, default=1)
    args = parser.parse_args()
    result = train_sgcc_live_model(args.input, args.model, args.metadata, seed=args.seed,
                                   target_recall=args.target_recall,
                                   windows_per_customer=args.windows_per_customer)
    print(json.dumps({"model_path": result["model_path"], "metadata_path": result["metadata_path"],
                      "threshold": result["threshold"], "metrics": result["metrics"]}, indent=2))

if __name__ == "__main__":
    main()
