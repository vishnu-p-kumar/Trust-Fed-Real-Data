from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ceew_dataset import ingest_ceew_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Stream and normalize local CEEW CSV/TSV smart-meter files.")
    parser.add_argument("--input", nargs="+", required=True, help="one or more source paths; paths may be absolute")
    parser.add_argument("--output", default="data/processed/ceew", help="normalized outputs and manifest directory")
    parser.add_argument("--mode", choices=["auto", "high_frequency", "daily_aggregate"], default="auto")
    parser.add_argument("--chunksize", type=int, default=100_000)
    parser.add_argument("--max-rows-per-file", type=int, default=None, help="optional smoke-run cap; manifest marks partial files")
    parser.add_argument("--profile-only", action="store_true", help="scan all rows and write only the manifest")
    args = parser.parse_args()
    manifest = ingest_ceew_files(args.input, args.output, mode=args.mode, chunksize=args.chunksize,
                                 max_rows_per_file=args.max_rows_per_file, write_normalized=not args.profile_only)
    print(json.dumps({"manifest": str(Path(args.output) / "ceew_manifest.json"),
                      "files": [{"source_file": row["source_file"], "rows": row["row_count_processed"],
                                 "meters": row["meter_count"], "mode": row["mode"]}
                                for row in manifest["files"]]}, indent=2))


if __name__ == "__main__":
    main()
