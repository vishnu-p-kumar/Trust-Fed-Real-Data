# Verification report — SGCC/CEEW live-telemetry release

Date: 2026-11-01

## Default data-source contract

- The default live theft classifier is trained from the labelled SGCC benchmark only. Its packaged model consumes a 30-calendar-day meter-consumption window converted into 26 fixed features. No synthetic examples are used to train this artifact.
- The admin federated-research endpoint (`POST /api/research/experiments`) now loads `datasets/sgcc/processed/sgcc_meter_features.csv.gz`, validates `meter_id` and `is_theft`, and passes the actual labelled SGCC table to the federated experiment. Customer-group holdouts are used. The response includes dataset provenance and `synthetic_training: false`.
- CEEW Mathura/Bareilly data trains the next-day consumption forecaster. CEEW theft labels are not present and no theft labels are invented.
- Synthetic data generation is opt-in through `--demo-synthetic`; it is not part of default model training or live telemetry inference. Synthetic classification fixtures remain available for explicitly invoked offline tests/controlled experiments.

## Packaged model results

### SGCC 30-day live theft classifier

- Dataset: 42,372 customers; 38,757 normal-labelled and 3,615 theft/abnormal-labelled.
- Model: HistGradientBoostingClassifier; 26 consumption-history features.
- Split: customer-disjoint train/validation/test; threshold selected on validation only.
- Test PR-AUC: **0.1662**.
- Test recall: **0.5007**; precision: **0.1313**; F1: **0.2081**; accuracy: **0.6749**; ROC-AUC: **0.6410**.
- Confusion matrix (TN, FP, FN, TP): 5,358 / 2,394 / 361 / 362.
- These results are a baseline only. The false-positive burden is high; this model is not production-ready and is not evidence of Indian utility theft accuracy. A meter is not classified until it has at least 30 calendar days and 20 valid daily readings.

### CEEW next-day consumption forecaster

- Source: supplied Mathura and Bareilly daily aggregates; 84 meters.
- Training / validation / test examples: 17,702 / 5,913 / 5,947.
- Test MAE: 1.6525 kWh; persistence MAE: 1.6781 kWh.
- Test RMSE: 2.9641 kWh; persistence RMSE: 3.1273 kWh.
- This is consumption forecasting, not theft detection. Forecast deviations are anomaly signals, not theft labels or proof.

## Functional verification

- `python run_project.py` completed the default SGCC + CEEW training orchestration with exit code 0. Training runs in separate child processes to constrain memory use.
- `python run_project.py --skip-training` completed and reported `LIVE TELEMETRY` mode.
- FastAPI live runtime startup, health endpoint, login/session authentication and dashboard APIs were exercised locally.
- Authenticated `POST /api/telemetry/readings` accepted 30 daily readings, generated an SGCC suspicion probability after warm-up, generated a CEEW next-day forecast, and persisted the history. Runtime re-bootstrap restored the meter history.
- `/ws/live` emitted a live snapshot. Ten operational dashboard endpoints returned HTTP 200 in the integration smoke test.
- Electrical range/power-factor checks can raise an early anomaly before the SGCC model has sufficient history; they do not assign a theft probability during warm-up.
- The actual admin federated-research endpoint was exercised using all 42,372 SGCC customer feature rows. It returned HTTP 200, ran the experiment, and reported `synthetic_training: false`, 42,372 rows, 42,372 unique meters, 46 numeric predictors and the expected label counts.
- Optional synthetic demo mode was smoke-tested separately, then its generated CSVs and runtime state were removed from the release.

## Automated checks

- Pytest: **154 passed** across two runs: 153 passed with the resource-heavy generalization test deselected; that test passed separately (1 passed). An unfiltered invocation intermittently stalled in this hosted runner after preceding ML tests, so no claim is made that the complete set passed in one process.
- Python compilation (`compileall`): passed.
- Dashboard JavaScript syntax checks (`node --check` for all JS files): passed.
- Requirements/configuration checks: passed.
- SGCC and CEEW model artifacts loaded successfully in the live runtime.

## Limitations

- No physical smart meter or utility gateway was connected. Live telemetry was tested with locally submitted HTTP readings only. A deployment needs an authenticated meter/IoT gateway (or broker adapter), device identity, secure transport, and validation of units, timestamps, resets and cumulative-register differencing.
- SGCC is a historical Chinese benchmark with published FLAG labels; the package does not include individual inspection records. Independent Indian theft labels are not available in the supplied CEEW data.
- The SGCC 30-day model's measured precision and PR-AUC are low. It must be improved and independently validated before operational decisions.
- Docker was unavailable in the verification environment; Compose build and container startup were not tested.
- PostgreSQL, Redis, email, Telegram and external weather integrations require infrastructure/API credentials and were not live-tested.
- This release is a research prototype, not a production-certified utility system. Human inspection remains necessary before enforcement or punitive action.
