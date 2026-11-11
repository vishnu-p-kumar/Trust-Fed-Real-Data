# GridSentinel independent validation report

**Validation date:** 2026-10-28  
**Repository state:** working tree after the research upgrade and validation fixes.  
**Scope:** source inspection, automated tests, import/dependency checks, a bounded generation/training workflow, and small federated experiments. This is not a production penetration test or a real-world theft-detection study.

Statuses below use the requested vocabulary: **PASS**, **FAIL**, **NOT VERIFIED**, and **NOT IMPLEMENTED**.

## 1. Executive summary

- **PASS — Core Python workflow:** imports resolved and a bounded command generated 3,360 rows, trained the classifiers/forecast models, and wrote the heatmap; exit code 0.
- **PASS — Automated suite:** the current `python -m pytest -q` completed with 76 passed, exit code 0. It emitted 4,131 warnings (mostly NumPy/joblib deprecations and one Starlette/httpx deprecation).
- **FAIL — Theft research validity:** the current synthetic generator and bounded central-model workflow do not support real-world theft-performance claims. The bounded run reported classification metrics of 1.0 on 672 held-out rows from only 20 synthetic meters; this is a synthetic sanity check. The supplied unlabeled CEEW data now has a chunked profile and a real-consumption federated forecast smoke study, but it cannot validate theft detection. Central application models still lack a nested temporal/group evaluation protocol.
- **PASS — Federated mechanics at prototype scale:** in-process client partitions, local updates, FedAvg, trimmed mean, trust-weighted aggregation, and result artifacts execute; mathematical unit tests cover key normalization and invalid inputs.
- **MIXED — Trust/defense follow-up:** the original zero-recall sign attack was reproduced and the detector was changed. The current 17-condition study uses five held-out synthetic seeds and leave-one-attack-family-out calibration. Utility-only recall ranges 0.90–1.00 for sign flips, 0.90–1.00 for label flips, and 0.20–0.40 for scale attacks. Benign FAR ranges 0–0.10; benign-shift FAR is 0.05–0.10 and label-flip 25% FAR is 0.133. A separate online-threshold smoke run falsely accused one of four benign clients (FAR 0.25). HATTA did not consistently beat trimmed mean.
- **NOT IMPLEMENTED — Formal privacy:** differential privacy and secure aggregation are explicitly disabled/absent.
- **NOT VERIFIED — Full service lifecycle and browser integration:** app import and route tests exist, but a real Uvicorn lifespan startup and interactive dashboard session were not exercised in this audit.
- **Overall readiness:** useful research software scaffold; not ready for a paper that claims robust trust-based federated theft detection. A paper can describe the prototype and its limitations, but efficacy, novelty, privacy, and production-readiness claims need further evidence.

## 2. Environment and commands used

Validation ran in the repository workspace on Windows with Python 3.14.5. Imported versions observed: FastAPI 0.140.1, pandas 3.0.3, NumPy 2.5.0, scikit-learn 1.9.0, and CPU PyTorch 2.14. The main app and federated experiment imports resolved and the app exposed 42 routes. Optional packages including XGBoost, TensorFlow, SHAP, Optuna, Evidently, GeoPandas, and Folium were not installed; guarded fallbacks let the main import and smoke workflow proceed.

Commands and results:

| Command | Result |
|---|---|
| `python -m pytest -q` (current tree) | **PASS**, exit 0, 76 passed, 4,131 warnings |
| CEEW full profile scan (eight CSVs; 200,000-row chunks) | **PASS**, scanned 21,439,039 records across high-frequency and overlapping daily aggregate files |
| CEEW daily-aggregate federated forecast | **PASS**, 84 meters; 34,011 examples; chronological 60/20/20; persistence baseline performed best |
| `python scripts/prepare_ceew_dataset.py --profile-only --chunksize 200000 --output reports/research_runs/ceew_profile --input <all eight supplied CSV paths>` | **PASS**, source files scanned without writing normalized readings |
| `python scripts/run_ceew_forecast.py --input <two normalized daily aggregate files> --interval 1D --clients 4 --rounds 3 --local-epochs 5 --learning-rate-candidates 0.01 0.03 0.05 0.1 --seeds 42 43 44 45 46 --output reports/research_runs/ceew_forecast.json` | **PASS**, selected learning rate per seed from validation FedAvg MAE; test evaluated afterward |
| `python scripts/run_trust_validation.py` | **PASS**, generated the 17-scenario JSON report with disjoint calibration/evaluation seeds |
| `python run_project.py --num-meters 20 --days 7 --forecast-epochs 1 --skip-report --skip-sample-export` | **PASS**, exit 0; 3,360 rows generated and models trained |
| Import check for FastAPI, pandas, NumPy, scikit-learn, PyTorch, `api.main:app`, and `src.federated.experiment:run_experiment` | **PASS**, exit 0 |
| `git diff --check` | **PASS**, exit 0 |
| `Test-Path` checks for the old Python 3.10 executable and old project directory in `run.md` | **FAIL** before documentation correction; both paths were absent |

`run.md` now uses repository-relative instructions and the Python environment on PATH. Optional packages are missing, so paths that specifically require them remain unverified.

## 3. Application startup results

- **PASS — Import/startup prerequisites:** `api.main` imports and constructs the FastAPI app. Its routes were enumerated in the import check.
- **PASS — Data generation and model training:** the bounded `run_project.py` command completed and wrote classifier/forecast artifacts and `maps/theft_heatmap.html`. Reported classification summary: 1.0 accuracy, precision, recall, F1, and ROC-AUC; 2,688 training rows, 672 evaluation rows, 38 features, using the `hist_gradient_boosting_fallback` model.
- **NOT VERIFIED — Actual Uvicorn startup/lifespan:** no live Uvicorn process was launched. The app lifespan can bootstrap full default data/model artifacts if missing, and was not exercised as a separate deployment lifecycle check.
- **PASS — SQLite/API-adjacent tests:** database and API behavior are covered by the test suite, but test clients patch bootstrap and authorization in some route tests. That coverage does not demonstrate a deployed service.
- **NOT VERIFIED — Dashboard in a browser:** no browser session was used to log in and exercise all dashboard screens against a live backend.

## 4. Test results, including failures

`python -m pytest -q` passed all 70 current tests. No test was removed or weakened during validation. Warnings included a Starlette/httpx deprecation and 4,130 NumPy/joblib deprecation warnings in the inspector workflow. The warnings did not fail tests but should be addressed through dependency compatibility and reduced repeated serialization warnings.

The first bounded pipeline attempt **failed** with exit code 1 when `predict_proba(... )[:, 1]` was applied to a single-class training split. Inspection confirmed the tiny generated dataset had only two positive meter groups and the prior split could put both in test. A customer-group stratified holdout was added in `src/federated/partition.py`, wired into `src/train_models.py`, `src/model_optimizer.py`, and `src/federated/experiment.py`, with a regression fixture in `tests/test_federated.py`. The rerun then passed. When meter groups exist but cannot support the required per-class split, the federated runner now raises an explanatory error instead of silently using a row split.

## 5. Federated learning verification

- **PASS — Partition coverage:** `partition_clients` creates deterministic, disjoint client index partitions; `tests/test_federated.py::test_partition_is_deterministic_and_disjoint` checks determinism and complete index coverage.
- **PASS — Local update path:** `src/federated/experiment.py::run_experiment` slices each client’s training partition, fits local logistic updates in the client loop, and passes update arrays to aggregators. The implementation is a single-process simulator, not a networked multi-organization system.
- **PASS — FedAvg math:** `src/federated/aggregators.py::fedavg` validates aligned finite updates and positive sizes, normalizes weights, and computes the weighted coordinate average. Unit tests verify a weighted example and reject malformed values.
- **PASS — Invalid updates:** `_clip_update` rejects nonfinite values/invalid norms; invalid local updates are skipped and recorded as `failed_clients`. Regression tests cover nonfinite rejection and clipping magnitude.
- **NOT VERIFIED — Raw-record isolation as an enforced boundary:** client loops exchange update arrays in code and do not serialize raw client rows to a coordinator. However, all simulated clients and coordinator execute in one process with shared memory; no process/network security boundary or packet capture was tested.
- **NOT VERIFIED — Saved-config reproduction:** config/results/checkpoint files are written. This audit did not perform a two-run byte-for-byte reproduction comparison. Timing is inherently variable, and the artifacts do not currently include a complete data hash/software lock manifest.
- **NOT VERIFIED — IID/non-IID comparative behavior:** partition modes are present, but the audit did not establish stable statistical differences across repeated seeds.

## 6. Trust algorithm verification

`src/federated/trust.py` measures positive validation log-loss harm and provides robust median/MAD thresholding plus threshold selection on calibration runs. `update_trust` remains a smoothing/recovery mechanism for non-flagged clients; harmful updates are downweighted using the validation-derived threshold. `normalized_weights` multiplies clipped trust by sample count and normalizes; when all trust scores are zero it falls back to sample-size weighting. Tests cover normalization, fallback, validation harm, threshold constraints, and recovery.

- **PASS — Formula/code consistency:** the scalar recurrence and aggregation weighting match the documented equations for valid inputs.
- **NOT IMPLEMENTED — Independent proof that honest non-IID outliers are never accused:** benign and shifted scenarios were added, but false accusations still occur. The standard one-seed online threshold falsely accused one of four honest clients under both benign and shifted conditions.
- **MIXED — Demonstrated malicious-client detection:** in the latest five-seed held-out synthetic study, sign-flip recall was 0.90–1.00, label-flip recall 0.90–1.00, and scale-attack recall 0.20–0.40 depending on strength/fraction. Honest FAR was nonzero, and online FAR was 0.25 in a smoke run. These results do not establish real-world performance.
- **NOT VERIFIED — Robustness of the trust weights:** utility is measured on coordinator-visible validation data from the global training split. Leakage of local records is avoided in the simulator’s update exchange, but this evaluation signal is a privacy and governance assumption and may unfairly penalize clients with shifted distributions.

## 7. Data leakage audit

- **PASS — Removed known direct leakage fields:** `src/federated/experiment.py` excludes the target, seeded probability, theft type, expected consumption, wastage fields, anomaly/risk outputs, meter ID, and timestamp from numeric predictors. `src/theft_detector.py` drops target and seeded generator labels from prediction output. `BASE_FEATURE_COLUMNS` was adjusted to exclude generator diagnostics.
- **PASS — Group holdout for meter IDs:** central training and federated supplied-data runs split by meter group when enough groups are present; preprocessing/scaling for the federated experiment is fitted on training rows only.
- **FAIL — Research split protocol is incomplete:** central `train_all_models` has a single train/test split and no separate validation split. The fixed 0.5 decision threshold is not validation-selected. `model_optimizer.py` evaluates candidate parameters on a holdout and the training path can reuse saved best parameters without a documented nested/untouched final test provenance. This can contaminate reported test performance when optimization is used.
- **FAIL — Forecast evaluation:** forecasters are trained from the enriched dataset in `train_all_models`; no held-out future-time metric is produced. Forecast result plots/output are not evidence of forecast generalization.
- **NOT VERIFIED — Future-information safety of every feature:** engineered rolling features were inspected and lagged where applicable, but no formal timestamp-sentinel test covers every feature or all generation/sample paths. The generator samples rows within each meter before model loading in some configurations, so temporal-window semantics require an explicit time-ordered evaluation audit.
- **NOT VERIFIED — Synthetic label separability:** the generator intentionally alters consumption, power factor, and voltage for theft periods, which makes the label identifiable by construction. The observed perfect bounded-run metrics warrant an ablation that removes each simulated clue and a separate generator-seed holdout before drawing any model-quality conclusion.

## 8. Attack experiment results

The earlier Step 3 sweep used one generated synthetic fixture (400 rows, 10 features, 4 clients, 3 rounds, 2 local epochs, severe label-skew, seed 42). It is retained as the **pre-fix** diagnosis, not the current detector result. F1 / PR-AUC were:

| Attack | FedAvg | Trimmed mean | Trust weighted | HATTA |
|---|---:|---:|---:|---:|
| None | 0.000 / 0.478 | 0.538 / 0.501 | 0.000 / 0.478 | 0.267 / 0.483 |
| Label flip, 25% malicious | 0.000 / 0.397 | 0.429 / 0.308 | 0.000 / 0.400 | 0.143 / 0.382 |
| Scale, 25% malicious | 0.182 / 0.501 | 0.545 / 0.492 | 0.182 / 0.510 | 0.143 / 0.487 |
| Sign flip, 25% malicious | 0.000 / 0.312 | 0.419 / 0.295 | 0.000 / 0.349 | 0.421 / 0.325 |
| Sign flip, 50% malicious | 0.000 / 0.279 | 0.238 / 0.153 | 0.000 / 0.310 | 0.356 / 0.217 |

Across those pre-fix cases, trust scoring flagged no malicious clients (precision/recall 0); `attack_success_rate` was null. This table remains a diagnostic record of the original failure.

### Post-fix calibrated evaluation

The latest five-calibration-seed (42–46), five-disjoint-evaluation-seed (52–56) study spans 17 benign, attack, distribution-shift, and recovery conditions, four trust-evidence modes, and four aggregation methods. Utility-only is the pre-specified primary evidence. Detection and model metrics for each condition, along with standard deviations, bounded 95% intervals, per-client results, calibration thresholds, and ablations, are recorded in the generated JSON and summarized in [TRUST_VALIDATION.md](TRUST_VALIDATION.md). Calibration excludes the evaluated attack family and does not use final test labels.

HATTA comparisons remain mixed across metrics and conditions. The latest study does not support superiority over trimmed mean. Attack success remains undefined and null for untargeted sign, scale, and label-flip scenarios.

- **NOT IMPLEMENTED — Attack success metric:** no target-specific attack success definition or rate is implemented.
- **MIXED — Recovery-after-attack experiment:** temporary sign attacks and a no-recovery comparison now run; final mean trust differed only modestly, so broader recovery benefit is unproven.
- **PASS WITH LIMITATIONS — Increasing attacker fractions and benign shifts:** repeated five-seed scenarios include sign/scale/label attacker fractions and moderate/severe benign feature shifts. False accusations remain measurable and nonzero; synthetic behavior does not prove distributional fairness.
- **NOT IMPLEMENTED — Backdoor, collusion, stale updates, and client-dropout attack protocols.**

## 9. Privacy implementation audit

- **NOT IMPLEMENTED — Differential privacy:** `run_experiment` explicitly records `privacy.enabled=false`; no noise mechanism, privacy unit, accountant, sampling assumptions, or composed epsilon/delta exists.
- **NOT IMPLEMENTED — Secure aggregation:** the coordinator receives per-client model deltas in the single process; there is no cryptographic aggregation protocol.
- **PASS — Documentation honesty:** current research metadata and `docs/PRIVACY.md` state that formal DP/secure aggregation are absent. No formal privacy claim is supported.
- **NOT VERIFIED — Operational secrets/history:** current `users.json` was removed and `.env` is ignored; `.env.example` uses environment variables. Earlier committed credentials may remain in Git history and require history review/rotation outside this audit. No live secret scan of every remote history/ref was done.

## 10. API and dashboard validation

- **PASS — Automated route checks:** `tests/test_api.py` exercises auth rejection and research API routes with test doubles; API source applies session/role checks to protected operations and validates bounded experiment inputs.
- **PASS — No hardcoded research score display identified:** dashboard research panel uses API experiment result fields; it does not provide a fixed benchmark score as a result.
- **NOT VERIFIED — Live API/dashboard contract:** frontend fetch behavior was inspected, but no browser login, live service call, disconnect, or full render check was run. Some test routes monkeypatch authorization and experiment execution.
- **NOT VERIFIED — Trust-history fidelity:** API returns the experiment’s stored trust data; a live client comparison against recomputed values was not run. Recorded per-round decisions are generated by code, but their attack-detection effectiveness failed in the sweep.
- **NOT VERIFIED — Error/disconnect behavior:** route input checks exist and tests cover selected bad requests; no end-to-end network fault simulation was run.
- **PASS — Demo label separation in prediction:** seeded probability is not used by the theft score blend, and demo alert overrides are gated. Research experiment code does not consume the operational detector’s forced/demo alert behavior.

## 11. Reproducibility assessment

- **PASS — Seeded core paths:** generation, partitioning, model constructors, and experiment config accept seeds; the group splitter is deterministic for fixed inputs.
- **PASS — Experiment artifacts:** `src/federated/experiment.py` writes config JSON, result JSON, per-round JSONL, and checkpoints when an output directory is requested.
- **NOT VERIFIED — Full reproducible research bundle:** the trust-study JSON records configurations, seeds, thresholds, split metadata, metrics, and confidence intervals, and the SGCC loader records source hashes. A dependency lock, source revision, CI matrix, and artifact replay comparison remain absent.
- **FAIL — Current evidence cannot reproduce a paper claim:** the repeated-seed synthetic study is reproducible, but there is no public-data acquisition or authorized SGCC experiment, fixed published split, or sufficient independent repetitions for a robust paper claim.

## 12. Confirmed defects fixed

1. **Single-class train split crash/invalid holdout:** implemented deterministic group-level stratified holdout in `src/federated/partition.py`; wired into central training, optimization, and supplied-data experiments. Added regression coverage. Bounded workflow rerun passes.
2. **All-zero trust aggregation crash/degenerate weights:** `src/federated/trust.py::normalized_weights` and `src/federated/aggregators.py::trust_weighted` now fall back to sample-size weights; tested.
3. **Invalid client sizes and updates:** FedAvg validates finite positive client sizes and finite updates; experiment clips/rejects nonfinite local updates and logs failed clients; tests added.
4. **Misleading training-row metadata:** central training records `training_rows` from the actual train partition and adds `evaluation_rows`.
5. **Prediction leakage surface:** theft prediction output no longer exposes the target, theft type, or seeded theft probability; direct generator/target fields were removed from feature selection.
6. **Stale run guide:** `run.md` no longer points to a different user’s Python 3.10 installation/project directory.
7. **Outdated limitation statement:** `docs/KNOWN_LIMITATIONS.md` now describes the group-split failure behavior and remaining API security review accurately.
8. **Trust detection failure:** replaced PR-AUC delta evidence and an arbitrary 0.40 floor with validation log-loss harm, calibrated thresholds on disjoint seeds, and auditable per-client decisions. Scaling misses and honest false accusations remain.

## 13. Unresolved issues and limitations

- A local SGCC wide-CSV loader, fixture tests, provenance hashes, and acquisition instructions exist. No authorized public dataset was supplied, so real-meter results remain absent; licensing terms must be verified by the user.
- Central evaluation needs train/validation/test protocol; tuning must be nested or use a final untouched test set; threshold and calibration need validation selection.
- Synthetic generation can make labels trivially recoverable from injected signals; require generator-seed and meter/time holdouts plus leakage/clue ablations.
- Demand forecasting has no future-time held-out evaluation.
- HATTA is provisional; trust evidence uses coordinator-visible validation utility, scaling recall was 0.40 in this small study, and false accusations remain nonzero.
- Targeted attack success remains undefined; broader benign accusation characterization under realistic shifts and stronger attack-cessation/recovery validation are needed. Synthetic federated confidence intervals exist but are based on only five evaluation seeds.
- No DP accountant/noise or secure aggregation. Single-process simulation provides no formal privacy boundary.
- Full Uvicorn lifespan startup, end-to-end login, and visual dashboard behavior remain unverified.
- Optional dependencies were unavailable; optional model/report/spatial paths were not independently executed.
- No broad security review for CSRF, rate limiting, production deployment, or historical secret exposure.
- Frequent NumPy/joblib and Starlette/httpx deprecation warnings remain.

## 14. Research-paper readiness assessment

**Status: NOT VERIFIED for theft-detection claims; NOT IMPLEMENTED for formal privacy.** The repository includes a five-seed-per-split synthetic trust study and a small real CEEW consumption-forecast run, but CEEW has no theft labels. Nested central-model evaluation, a targeted attack-success measure, and formal privacy mechanisms are still absent. HATTA does not consistently outperform trimmed mean. Novelty is **NOT VERIFIED** and needs focused literature review and comparisons. Passing tests does not establish scientific validity or novelty.

## 15. Exact next actions

1. Acquire or obtain permission to use a public dataset with verified theft labels; keep CEEW for unlabeled consumption/supply research and do not infer theft labels from it.
2. Implement group-disjoint train/validation/test splits and nested model selection; fit encoders/scalers only on training data; select thresholds/calibration on validation only.
3. Add temporal sentinel tests for every engineered feature and a future-time forecasting evaluation; assess random sampling’s impact on temporal windows.
4. Expand repeated-seed evaluation substantially and report confidence intervals for PR-AUC, recall at fixed false-positive rate, F1, calibration, and per-client distributions.
5. Define and test threat models for label flipping, sign/scale/update manipulation, targeted backdoor, collusion, dropout, and attacks that stop; define attack success and recovery metrics before experiments.
6. Evaluate benign client shifts separately; report malicious detection precision/recall and honest false-accusation rates. Compare trust features and aggregation methods with ablations.
7. Add a reproducible run manifest (revision, dependency lock, data hash, config, split IDs, seeds, runtime, hardware) and a replay test.
8. Decide whether privacy is a research contribution. If so, implement user-level clipping/noise with a vetted accountant and explicit composition assumptions, or secure aggregation, then test the stated threat model. Otherwise keep privacy claims limited to the simulator’s data-flow design.
9. Add live Uvicorn lifespan/API smoke tests with isolated temporary storage, full valid-login/dashboard browser integration, and network failure coverage.
10. Review CSRF/rate limits/deployment settings and rotate any secrets present in repository history; resolve dependency deprecation warnings and pin compatible versions.

### Final disposition

The bounded application workflow runs, and all 76 automated tests pass. The original trust failure was reproduced and mitigated for sign flips and label flips in a small calibrated synthetic study, while scaling attacks remain difficult and honest false accusations persist. The CEEW data integration supports real consumption forecasting but not theft evaluation; persistence beat the trained methods in the reported test run. The current results do not support real-world theft detection or HATTA superiority claims. Formal privacy, live app/dashboard validation, and paper-grade evaluation remain outstanding.

## 16. CEEW dataset integration

All eight supplied CEEW CSVs were inspected and streamed in 200,000-row chunks. The ingestion manifest records SHA-256, time coverage, meter counts, missing/invalid readings, zeros, duplicates, and interval frequencies without recording meter IDs or absolute source paths. The output is in `reports/research_runs/ceew_profile/ceew_manifest.json`. Daily aggregate data was normalized and used for a five-seed, four-client real-consumption forecast comparison; mean FedAvg MAE was 2.133 kWh while previous-reading persistence MAE was 1.979 kWh. A separate two-client city split pilot also ran. These negative comparisons are preserved. The five seeds vary meter-to-client assignment over the same chronological split, so intervals show assignment sensitivity only. The 99th-percentile residual threshold was chosen from validation and is an unlabeled anomaly proxy only. The supplied files have no verified theft labels. Full schema, profile details, reproducible commands, and caveats are in [DATASET_CARD.md](DATASET_CARD.md).
