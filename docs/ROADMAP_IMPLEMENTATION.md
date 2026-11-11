# GridSentinel roadmap implementation and remaining production gates

This release adds working utilities for leakage-aware benchmark evaluation, dataset provenance checks, a single-release Gaussian mechanism, a pairwise-mask aggregation simulation, a durable single-host SQLite job queue, browser security middleware, and a more explicit investigation warning in the dashboard.

## 1. Labeled theft data: what is and is not supplied

No independently verified Indian electricity-theft labels are bundled. The included CEEW Mathura/Bareilly dataset measures smart-meter consumption and supply conditions but does not provide verified theft labels. The project therefore must not claim that CEEW validates supervised theft classification.

A widely used public research benchmark is the State Grid Corporation of China (SGCC) theft-detection dataset, described by the IEEE PES Data Sharing site as 42,372 consumers over 1,035 days. Public access is listed, but the page lists no license. Confirm access terms and cite the original source before redistribution or commercial use. It is not an Indian dataset, and its labels may still have inspection errors or ascertainment bias.

- Dataset record: https://ieee-pes-data-sharing.org/datasets/detail/663b8e0e-3ace-48f8-b983-4cb59b39fa6f
- CEEW India smart-meter dataset (unlabeled for theft): https://doi.org/10.7910/DVN/GOCHJH

Do not add a downloaded dataset to this ZIP without checking license and redistribution rights. To validate a supplied labeled CSV:

```powershell
python scripts/validate_theft_dataset.py --input data/labels/sgcc.csv --manifest data/labels/sgcc.provenance.json
python scripts/evaluate_theft_models.py --input data/labels/sgcc.csv --output reports/research_runs/theft_benchmark.json
```

The provenance manifest must contain `source_name`, `source_url`, `license`, `label_provenance`, and `label_verification`. This validates the declared provenance and file shape; it cannot independently prove label truth. For an SGCC-style wide CSV, expected columns are a consumer ID, daily numeric columns, and a binary label such as `flag`. The benchmark excludes the identifier and target from features and holds out entire customers.

Example manifest template:

```json
{
  "source_name": "State Grid Corporation of China electricity theft benchmark",
  "source_url": "https://ieee-pes-data-sharing.org/datasets/detail/663b8e0e-3ace-48f8-b983-4cb59b39fa6f",
  "license": "Confirm with dataset provider; public access page lists no license",
  "label_provenance": "Describe source label field and collection process",
  "label_verification": "Document inspection/utility confirmation evidence and known limitations"
}
```

## 2. Evaluation and leakage prevention

`evaluate_theft_models.py` uses a customer-disjoint split, drops target/ID columns, fits imputers and scalers inside sklearn pipelines on training rows only, fixes threshold at 0.5 before the test evaluation, and reports precision, recall, F1, balanced accuracy, ROC-AUC, average precision, and confusion-matrix counts. A single split is not sufficient for final scientific claims; repeat with pre-registered seeds and report variability.

`evaluate_forecasting.py` compares persistence, seasonal-naive, and expanding-mean baselines on a chronological split. The LSTM training scaler is now fit only on the chronological training segment and training is not shuffled. Learned models still need to be benchmarked on the same held-out timestamps before claiming improvement.

## 3. Privacy mechanisms

`src/security/privacy.py` implements L2 clipping plus Gaussian noise for a single aggregate release and a pairwise-mask secure-sum simulation. The DP helper returns a classical single-release bound and explicitly states that it does not account for multiple training rounds. Production DP requires a vetted Rényi/PRV accountant and an explicit sampling/adjacency model. The pairwise mask simulation is not a production secure-aggregation protocol: key exchange, authenticated clients, dropout handling, collusion analysis, replay resistance, transport security, and cryptographic review remain required.

## 4. Durable jobs and persistence

`src/jobs/sqlite_queue.py` provides an atomic, durable local job queue with queued/running/completed/failed states. It is not yet wired to all API operations and is intended for single-host/local use. For multi-worker production, use a shared queue/broker and a worker service. The app still uses SQLite helpers for runtime tables. PostgreSQL migration, schema migrations, backup/restore drills and multi-instance testing remain deployment tasks.

## 5. Browser security controls

The API now rejects browser state-changing requests carrying an Origin outside the configured allowlist, applies a basic per-process login attempt limit, and emits baseline security headers. These controls complement but do not replace endpoint authorization, TLS, reverse-proxy limits, centralized rate limiting, secret management, CSRF testing, audit logging, and security review. The rate limiter is per-process and resets on restart. Configure `SMARTGRID_CORS_ORIGINS` to match the exact origin serving the app.

For local HTTP only, set `SMARTGRID_COOKIE_SECURE=0`. For HTTPS deployment, keep secure cookies enabled. Do not use example passwords or commit secrets.

## 6. Model artifact compatibility

The saved scikit-learn artifacts report version 1.9.0 while some environments may have another version. The requirements now pin scikit-learn 1.9.0 to match the recorded artifact version. Run:

```powershell
python scripts/check_model_compatibility.py
```

Review `reports/model_compatibility.json`. Do not blindly re-save old pickle files to silence warnings. If the matching version cannot be installed, retrain artifacts from versioned data and configuration in the target environment, then evaluate before replacing deployed files. Only load trusted model files because pickle/joblib loading can execute code.

## 7. Dashboard investigation workflow

The theft-detection view now states that a score/anomaly is not proof of theft and escapes data-derived table text before rendering. Existing inspector task assignment/completion workflow remains the primary case workflow. For a production rollout, persist case acknowledgement/ownership/SLA transitions in a normalized database table, add audit history and authorization tests, and require human review before enforcement decisions.

## 8. End-to-end release gate

The automated unit suite is not equivalent to a production deployment test. Before release, run the test suite in the pinned environment, run `python scripts/check_model_compatibility.py`, start Uvicorn in a fresh environment, verify login/logout, dashboard data loading, WebSocket reconnects, prediction and inspection flows, and test a restart with the runtime database present. Production readiness also requires load tests, dependency vulnerability scanning, backup/restore validation, TLS and secret rotation.
