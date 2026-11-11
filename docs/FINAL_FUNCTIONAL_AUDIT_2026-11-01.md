# Final functional audit — 1 November 2026

## Scope

This audit was performed against a fresh extraction of `Trust-Fed-Grid-X-PR-AUC-Cross-Utility-Upgrade.zip`, not against an unrelated working tree. The extracted project was corrected, run with its default demonstration configuration, tested through its HTTP API, and repackaged. The final archive is intended as a research/demo prototype, not a production-certified electricity utility system.

## Corrections made during audit

1. `src/sample_outputs.py` previously exported `is_theft`, `theft_type`, and `seeded_theft_probability` in `predict_request.json`. The public `MeterReading` inference schema rejects these label/internal fields. They are now excluded, both checked-in and regenerated example requests were sanitized, and a regression test validates the generated request against the actual Pydantic schema.
2. `ResearchExperimentRequest.attack` omitted the implemented `low_slow` and `adaptive_mimic` adversarial modes. The API now accepts both; schema and live HTTP experiment checks passed.
3. `.env.example` and `requirements-advanced.txt` contained literal `\\n` text instead of line breaks in appended configuration sections. These files have been repaired and all requirement lines parse successfully.
4. The example CORS allow-list now includes the direct local API origins on port 8000 as well as the listed 8080 origins, matching the local setup instructions.
5. Docker Compose now passes the configured admin identity/password, session-signing secret, cookie mode, CORS allow-list, demo mode and alert mode into the API container. The Docker instructions now require a local `.env` file with non-placeholder secrets. This wiring was inspected and documented, but Docker Compose could not be executed because Docker is unavailable in the audit runtime.

## Automated verification

- `python -m pytest -q`: **147 passed in 33.97 seconds** on the extracted project.
- `python -m compileall -q api src scripts tests utils`: passed.
- All dashboard JavaScript files passed `node --check`.
- `requirements.txt`, `requirements-test.txt`, and `requirements-advanced.txt`: all requirement entries parsed successfully.
- `scripts/check_model_compatibility.py`: Isolation Forest, Random Forest, and XGBoost artifacts all loaded successfully in the audit environment.
- ZIP archive integrity: passed before final packaging; the final ZIP is separately verified after creation.

## Main application pipeline

Command executed:

```bash
python run_project.py --forecast-epochs 5
```

Result:

- Generated 45,000 synthetic smart-meter rows for the default 500-meter, 60-day demonstration configuration.
- Trained detection models using 36,024 training rows and 8,976 evaluation rows with 44 engineered features.
- Generated `sample_outputs/generated/`, the PDF daily report, the theft heatmap, and model/runtime artifacts.
- The synthetic classification split reported 1.0 across its headline metrics. This is a result on generated data and is **not** evidence of real-world theft-detection accuracy.

## Live API and workflow checks

A real Uvicorn process was started from the extracted project. `GET /health` returned `status=ok` and reported the expected runtime artifacts as present. Authenticated API checks returned HTTP 200 for overview, meters, anomalies, theft records, weather impact, forecast, risk scores, efficiency, pole status/tamper/energy balance, drift reporting, admin trust/audit/investigations/analytics, inspectors, and report/heatmap/sample artifact downloads.

Additional workflow checks:

- Admin login, session validation, and logout passed. An authenticated route returned HTTP 401 after logout.
- The bundled/generated sample request initially reproduced HTTP 422; after correction, `POST /predict` returned HTTP 200 with one prediction record.
- Untrusted cross-origin state-changing request was rejected with HTTP 403.
- Client onboarding, client login, dataset-metadata registration, client update submission, coordinator aggregation, and global-model version increment passed. The benign test update achieved coordinator AUC 1.0 on the synthetic coordinator validation data; this validates the workflow only, not a generalised model claim.
- `low_slow` and `adaptive_mimic` experiment requests both completed through the authenticated research API with HTTP 200.
- Inspector creation/login, inspector dashboard/case lookup, task assignment, and task completion all returned HTTP 200.
- The tamper-evident audit log verification returned `valid=true`.

The generated audit client/inspector accounts and temporary audit databases are not included in the final package.

## Research workflow smoke runs

The following command-line paths completed using reduced smoke settings. Their JSON outputs are included under `reports/functional_audit/`:

- Federated comparison: 16 runs, two seeds, two partition conditions.
- Robustness suite: 24 runs across 12 scenarios.
- Privacy utility suite: 12 runs plus 12 trust-evidence runs, six noise multipliers, two seeds.
- SGCC adversarial suite: 14 runs across seven scenarios, 500 sampled customers.
- Edge-efficiency proxy: 1,200 sampled customers, ExtraTrees and HistGradientBoosting.
- Validation-only permutation explanation: 1,200 sampled customers.
- CEEW distribution-shift audit completed on the full supplied aggregated cohorts: 38 Mathura meters and 46 Bareilly meters, with 12 comparable profile statistics.
- PR-AUC optimisation code completed on a deterministic 3,600-customer stratified SGCC smoke sample across three seeds. This verifies the model-selection/threshold pipeline code path, but is not the full-cohort benchmark.

The full-cohort SGCC PR-AUC results file already present in `reports/research_runs/sgcc_pr_auc_optimisation.json` is retained. A fresh three-seed recomputation over all 42,372 customers exceeded the execution limit in this audit environment; therefore the included full-cohort report was not independently regenerated during this final audit. Do not substitute the smaller smoke-sample figures for the full-cohort result.

## Environment-dependent checks and remaining limitations

- TensorFlow was not installed in this audit runtime. The LSTM forecasting module's documented baseline fallback was exercised; the installed PyTorch path was available and the transformer forecast metadata identified a transformer model. A clean environment installing `requirements.txt` is expected to install TensorFlow, but that installation was not performed here.
- Docker/Docker Compose could not be run because the Docker executable was unavailable in the environment.
- Browser visual/end-to-end automation was not available. Dashboard assets were served successfully and JavaScript syntax was checked, but pixel-level UI behavior was not certified in a browser automation suite.
- The optional TDD2022 external dataset was not bundled or downloaded. Its evaluator remains an optional path requiring a separate dataset acquisition.
- Docker Compose and the `production` profile were not run because the Docker executable is unavailable in this environment. The Compose environment wiring was corrected, but a host with Docker must still validate image builds and container startup.
- CEEW records have no verified theft labels, so CEEW results are feature-distribution shift only; no CEEW theft PR-AUC is claimed. SGCC is a historical Chinese benchmark, not independently verified Indian utility theft data.
- External weather, email, Telegram, PostgreSQL, Redis, production TLS, multi-worker deployments, load testing, penetration testing, formal cryptographic review, and production secure-aggregation/DP certification require credentials, infrastructure, or independent review not available during this audit.

## Final assessment

The default synthetic demonstration pipeline, API startup, prediction endpoint, dashboard-serving endpoints, primary admin/client/inspector workflows, adversarial experiment API modes, and automated tests are working in the audited environment. The archive should be described as a **fully tested research/demo prototype within the checks listed above**, not as production-ready or as independently field-validated theft detection.
