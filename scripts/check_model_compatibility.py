"""Report serialized model compatibility warnings without silently modifying artifacts."""
from __future__ import annotations
import json, warnings
from pathlib import Path
import joblib
import sklearn

ROOT = Path(__file__).resolve().parents[1]

def main() -> None:
    report = {"python_sklearn_version": sklearn.__version__, "artifacts": [],
              "note": "Loading pickle/joblib artifacts from an untrusted source can execute code. Only inspect trusted project artifacts."}
    for path in sorted((ROOT / "models").glob("*.pkl")):
        item = {"file": path.name, "size_bytes": path.stat().st_size, "loadable": False, "warnings": []}
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            try:
                model = joblib.load(path)
                item["loadable"] = model is not None
            except Exception as exc:
                item["error"] = f"{type(exc).__name__}: {exc}"
            item["warnings"] = [str(w.message) for w in captured]
        item["compatibility_status"] = "warning" if item["warnings"] else ("loadable" if item["loadable"] else "failed")
        report["artifacts"].append(item)
    output = ROOT / "reports" / "model_compatibility.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
