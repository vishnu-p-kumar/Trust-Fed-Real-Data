# Live SGCC + CEEW Architecture Upgrade (2026-11-01)

## Purpose

The default Trust-Fed-Grid-X runtime no longer generates synthetic data or trains its primary theft classifier on synthetic labels. It now uses three clearly separated data paths:

1. **SGCC labelled historical benchmark** — supervised electricity-theft/abnormality classification.
2. **CEEW Mathura + Bareilly daily aggregates** — next-day consumption forecasting only; no theft labels are used.
3. **Incoming meter telemetry** — live inference input. A telemetry gateway posts interval energy readings to the API; the runtime maintains per-meter daily histories and scores them using the SGCC-trained model.

Synthetic generation remains available only through the explicit `--demo-synthetic` option and test fixtures. It is not part of default model training or default inference.

## Model training and measured results

### SGCC live theft classifier

- Source: `datasets/sgcc/raw/sgcc_data.csv`.
- Model: `HistGradientBoostingClassifier`.
- Input: a fixed 30-calendar-day profile with 26 consumption-derived features.
- Sampling: one deterministic 30-day window per SGCC customer for the packaged baseline; customer IDs are disjoint across training, validation and test partitions.
- Threshold: selected on validation data to target recall of at least 0.40; the test set is not used for threshold selection.
- Artifact: `models/sgcc_live_theft_model.pkl` and `models/sgcc_live_theft_metadata.json`.

Packaged baseline test metrics (customer-level holdout, 8,475 test customers):

| Metric | Value |
|---|---:|
| Accuracy | 0.6749 |
| Precision | 0.1314 |
| Recall | 0.5007 |
| F1 | 0.2081 |
| PR-AUC (average precision) | 0.1662 |
| ROC-AUC | 0.6410 |
| Confusion matrix (TN, FP, FN, TP) | 5,358; 2,394; 361; 362 |
| Selected threshold | 0.1058 |

The false-positive burden is high and the PR-AUC is modest. This is a baseline demonstrating the end-to-end SGCC-to-live-inference connection, not a production-quality classifier. These results are not directly comparable to the previous full-profile SGCC benchmark because the live model is deliberately trained on a 30-day history window so it can operate on rolling incoming telemetry. The source data is a historical Chinese benchmark; it does not include independent per-customer inspection logs in this package.

### CEEW consumption forecaster

- Sources: `datasets/ceew/raw/SM Cleaned Data MH Aggregated.csv` and `datasets/ceew/raw/SM Cleaned Data BR Aggregated.csv`.
- Task: next-day energy-consumption forecasting.
- Inputs: seven previous valid daily kWh readings and weekday calendar features.
- The learned model is selected only when validation MAE improves on a persistence baseline; otherwise the persistence baseline is used.
- Artifact: `models/ceew_consumption_forecaster.pkl` and `models/ceew_consumption_forecaster_metadata.json`.

Packaged forecast training/evaluation summary:

- 17,702 training examples; 5,913 validation examples; 5,947 chronological test examples.
- 84 meters represented.
- Validation MAE: learned model 1.3969 kWh; persistence 1.4253 kWh.
- Test MAE: learned model 1.6525 kWh; persistence 1.6781 kWh.
- Test RMSE: learned model 2.9641 kWh; persistence 3.1273 kWh.

CEEW has no verified theft labels in the supplied files. Forecast deviations are not theft labels or proof of theft.

## Live telemetry interface

The default runtime mode is `live_telemetry`. It does not read or replay `data/processed/live_simulation.csv`.

Authenticated endpoint:

`POST /api/telemetry/readings`

The request body is a JSON array (up to 500 records per request). A minimal record is:

```json
{
  "meter_id": "METER-001",
  "timestamp": "2026-10-01T10:15:00Z",
  "consumption_kwh": 0.125,
  "voltage": 230.1,
  "current": 1.8,
  "power_factor": 0.96,
  "area": "Area-1",
  "region": "Bengaluru"
}
```

`consumption_kwh` means energy consumed during that interval, not the meter's cumulative lifetime register. If a physical meter reports a cumulative register, the gateway must difference successive register values, handle resets/rollovers and then send non-negative interval kWh. The server aggregates interval readings into daily kWh per meter and persists readings in the local SQLite telemetry table.

### Warm-up and output semantics

- Theft classification becomes available after at least **30 calendar days** of history and **20 valid daily readings** in the rolling window.
- Before that point, the output is `Insufficient History`; the system does not call the meter normal merely because history is missing.
- Electrical range / power-factor checks may raise an early `Anomaly` signal before the classifier is ready. Such a signal is explicitly not a theft classification.
- CEEW next-day forecasting requires at least **seven valid daily readings**.
- A model result is a suspicion score to support investigation, not proof of theft. Human inspection and utility-authorised evidence remain necessary.

The HTTP API is the implemented ingestion path. The application package does not include a configured physical smart-meter deployment, broker credentials, or a validated MQTT gateway. A real utility must connect its meter/IoT gateway to this endpoint (or implement a broker adapter) and verify payload units, timestamps, authentication, network security and device identity.

## Commands

From the project root:

```bash
python -m pip install -r requirements.txt
python scripts/train_sgcc_live_model.py --windows-per-customer 1 --target-recall 0.40
python scripts/train_ceew_forecaster.py
python run_project.py --skip-training --start-api
```

The default training command is also:

```bash
python run_project.py
```

To intentionally use the legacy synthetic dashboard demonstration (not the default and not research evidence):

```bash
python run_project.py --demo-synthetic --num-meters 20 --days 7 --forecast-epochs 1
```

## Verification scope and limitations

The regression suite includes the SGCC feature schema, model provenance guard, minimum-history behaviour, CEEW forecast readiness, telemetry ingestion, health payload and API integration paths. The live API was exercised using submitted test telemetry; no physical meter or utility network was available. Docker was not installed in the verification environment, so a real container build/start could not be tested. This is a research prototype, not a certified or production-ready utility system.

## Final verification record

The following checks were run against the updated working copy on 2026-11-01:

- Default model-training orchestration completed successfully with exit code 0. The SGCC trainer and CEEW trainer were run as separate child processes to release the sizeable SGCC/pandas allocation before CEEW training.
- `python run_project.py --skip-training` exited successfully and reported `LIVE TELEMETRY` mode.
- Full test coverage was executed in two batches: 153 tests passed with the generalization-evaluator test deselected, and that remaining generalization-evaluator test passed separately. Thus all 154 collected test cases passed across the two runs.
- Python bytecode compilation and dashboard JavaScript syntax checks passed.
- The actual Uvicorn process started from `run_project.py --skip-training --start-api`; `/health` returned `ok`, `live_telemetry`, and the SGCC-labelled source with both SGCC and CEEW artifacts present.
- Authenticated API integration accepted 30 daily readings for a meter, produced an SGCC suspicion probability and a CEEW next-day forecast, and returned HTTP 200 from 10 operational endpoints. The persisted telemetry history was restored after calling the runtime bootstrap again.
- The optional synthetic demonstration mode was separately smoke-tested with 20 meters and seven days, generating 3,360 rows. This output was removed before packaging and is not a default runtime source.

An unfiltered pytest invocation intermittently stalled in this hosted environment around the generalization-evaluator test after preceding ML tests; the remaining test was therefore also run independently and passed. The two-batch method covers all 154 collected tests. Docker was not installed, so a real Docker/Compose build and container startup were not verified. No physical meter, gateway or utility network was connected; the HTTP telemetry path was exercised using test readings. These limitations do not change the passing local API and code checks, but they prevent claiming a field deployment or production certification.


## Federated research experiment data source

The default authenticated admin route `POST /api/research/experiments` loads `datasets/sgcc/processed/sgcc_meter_features.csv.gz` and passes that labelled customer table to `src.federated.experiment.run_experiment`. The API validates the `meter_id` and `is_theft` columns, then uses customer-group holdouts so records from one customer do not cross the train/validation/test boundaries. Its response includes `dataset_provenance`, including row count, unique customers, numeric predictor count, label counts and `synthetic_training: false`.

Calling `run_experiment()` directly without its `dataframe` argument still creates a `make_classification` fixture by design. That is retained for explicit offline smoke tests and controlled synthetic robustness experiments; it is not the default API research path or the default live theft model training source.
