from __future__ import annotations
import argparse, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.ceew_forecaster import train_ceew_forecaster

def main() -> None:
    parser = argparse.ArgumentParser(description="Train a next-day consumption forecaster using CEEW Mathura/Bareilly daily aggregates.")
    parser.add_argument("--mathura", type=Path, default=ROOT / "datasets/ceew/raw/SM Cleaned Data MH Aggregated.csv")
    parser.add_argument("--bareilly", type=Path, default=ROOT / "datasets/ceew/raw/SM Cleaned Data BR Aggregated.csv")
    parser.add_argument("--model", type=Path, default=ROOT / "models/ceew_consumption_forecaster.pkl")
    parser.add_argument("--metadata", type=Path, default=ROOT / "models/ceew_consumption_forecaster_metadata.json")
    args = parser.parse_args()
    result = train_ceew_forecaster([args.mathura, args.bareilly], args.model, args.metadata)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
