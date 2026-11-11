> **Superseding addendum:** This report reflects the two datasets uploaded after the original validation report was prepared. It supersedes earlier statements that no SGCC or CEEW source data had been supplied. Earlier synthetic benchmark results remain synthetic and are not replaced by these real-data results.

# Uploaded real-world dataset evaluation — 2026-11-01

## SGCC benchmark audit

- Source: uploaded `ElectricityTheftDetection(1).zip`, extracted from the three split-archive members.
- Rows/customers: 42,372; unique IDs: 42,372.
- Labels: 38,757 normal (`FLAG=0`), 3,615 theft/abnormal (`FLAG=1`), positive rate 8.53%.
- Daily columns: 1,034; dates: 2014-01-01 to 2016-10-31.
- Missing consumption cells: 11,233,528 / 43,812,648 (25.64%).
- Zero readings among observed cells: 17.77%; negative readings: 0.
- Raw CSV SHA-256: `99f8fd315626b1f729a9a03a97cb52ed097ab4d43e5771e21554c9e0c369b9b7`.

The uploaded README cites Zheng et al. (IEEE TII, 2018), DOI `10.1109/TII.2017.2785963`. Published SGCC dataset descriptions report the same customer and class counts and the same collection period. Literature also describes SGCC field inspection of normal/abnormal customers; however, this uploaded package does not contain customer-level inspection records or adjudication logs. Treat results as **SGCC-labelled benchmark results**, not independently re-audited inspection outcomes.

## Preprocessing and split protocol

- `scripts/prepare_sgcc_dataset.py` generated one row per customer with 37 label-independent statistical/time-profile features.
- Features include mean/std/quantiles, zero/missing rates, early/late windows, trend, month-of-year and year means.
- Five seeds: 11, 23, 37, 53, 71.
- Each run uses an 80/20 customer-disjoint holdout; each customer appears in exactly one row, and overlap is checked.
- Fixed decision threshold 0.5. Imputation/scaling are fitted only on training customers; missingness indicators are included in the federated pipeline.

## Five-seed centralized baseline results

| Model | Accuracy | Precision | Recall | F1 | PR-AUC | ROC-AUC | FPR | MCC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| logistic regression | 0.757 | 0.192 | 0.584 | 0.289 | 0.278 | 0.748 | 0.227 | 0.227 |
| random forest | 0.910 | 0.452 | 0.282 | 0.347 | 0.347 | 0.792 | 0.032 | 0.311 |
| hist gradient boosting | 0.921 | 0.650 | 0.145 | 0.237 | 0.375 | 0.804 | 0.007 | 0.282 |

Five-seed 95% t confidence intervals are retained per metric in `reports/research_runs/sgcc_customer_disjoint_benchmark.json`.

Interpretation: HistGradientBoosting has the highest PR-AUC (0.375) and precision (0.650), but recall is only 0.145. Random Forest has the best F1 (0.347) and MCC (0.311), but recall is only 0.282. Logistic Regression has higher recall (0.584) at a much higher false-positive rate (0.227). High accuracy is not a sufficient success measure under the 8.53% positive class.

## Three-seed federated pilot on SGCC

Config: 4 clients, severe non-IID partition, 2 communication rounds, 1 local epoch, benign/no attack, seeds 11/23/37. This is an exploratory pilot, not a publication-grade convergence study.

| Method | Accuracy | Precision | Recall | F1 | PR-AUC | ROC-AUC | FPR |
|---|---:|---:|---:|---:|---:|---:|---:|
| centralized | 0.898 | 0.351 | 0.203 | 0.253 | 0.216 | 0.685 | 0.037 |
| fedavg | 0.909 | 0.487 | 0.104 | 0.148 | 0.188 | 0.625 | 0.016 |
| fedprox | 0.850 | 0.430 | 0.189 | 0.136 | 0.178 | 0.618 | 0.088 |
| trimmed mean | 0.612 | 0.122 | 0.555 | 0.199 | 0.179 | 0.621 | 0.383 |
| multi krum | 0.643 | 0.118 | 0.491 | 0.190 | 0.141 | 0.618 | 0.343 |
| trust | 0.909 | 0.514 | 0.107 | 0.150 | 0.185 | 0.622 | 0.016 |
| hatta | 0.774 | 0.315 | 0.261 | 0.213 | 0.205 | 0.635 | 0.178 |

HATTA does not establish superiority in this pilot. Its mean F1 is lower than the centralized reference and only modestly above FedAvg; Trimmed Mean has higher recall but a substantially higher false-positive rate. The results are affected by the short two-round configuration.

## CEEW uploaded data audit and processing

The uploaded `archive.zip` is truncated and has no central directory. `scripts/recover_ceew_zip.py` recovers complete ZIP members using local headers, ZIP64 sizes and CRC32 checks. Seven members were recovered and CRC-verified; `SM Cleaned Data MH2021.csv` is incomplete (379,707 bytes of its 4,511,143-byte compressed payload remain) and was excluded.

CEEW fields: high-frequency files have timestamp, kWh, average voltage, current, frequency and meter ID; aggregated files have meter, date and kWh. No theft ground-truth labels are present. These files are used only for consumption forecasting, meter heterogeneity and anomaly-proxy analysis.

## Data and legal limitations

- SGCC is a historical China utility benchmark, not a live stream and not Indian utility data.
- The uploaded SGCC README requests citation but does not specify an explicit dataset redistribution licence; verify upstream terms before redistributing raw data.
- CEEW is unlabeled for theft; never calculate supervised theft precision/recall from it.
- Metrics are conditional on the benchmark labels and selected features; external utility validation is still needed.
- No performance target or accuracy value was manually forced. Reports preserve measured metrics and confidence intervals.

### CEEW full-ingestion audit (seven recovered files)

- Total rows processed: 20,888,479.
- Distinct meters by location: Bareilly 46; Mathura 38.
- High-frequency modal interval: 180 seconds (3 minutes); irregular long gaps are retained.
- Two daily aggregate files were ingested separately from high-frequency files.
- All source rows had parseable timestamps; no negative values were found in the audited numeric fields.
- Source files and their SHA-256 checksums, row counts, time spans, missing-value counts, and interval distributions are recorded in `datasets/ceew/processed/ceew_manifest.json`.
- Duplicate checks are chunk-local and adjacent-chunk-boundary checks, not a global deduplication proof.

### CEEW high-frequency forecasting pilot

A bounded pilot used the first 500,000 rows from each of five high-frequency source files (2.5 million source rows before forecasting-example construction), with 4 federated clients, 2 rounds, 1 local epoch and two client-assignment seeds. The chronological meter-level test set contained 498,948 next-reading examples per run.

| Test predictor | MAE (kWh) | RMSE (kWh) | WAPE |
|---|---:|---:|---:|
| Persistence (last reading) | 0.00402 | 0.01152 | 0.197 |
| FedAvg | 0.01985 | 0.03221 | 0.971 |
| Centralized | 0.01985 | 0.03221 | 0.971 |
| Trimmed Mean | 0.01997 | 0.03230 | 0.977 |
| Local-only | 0.01986 | 0.03217 | 0.972 |

The simple persistence baseline substantially outperformed the current federated/centralized linear forecasters. This is a negative result: the current forecasting model needs redesign or calibration before it can be considered useful. The pilot is a prefix sample of each file, not a representative random sample of all 20.9 million CEEW readings. The full chunked ingestion audit is complete and covers all seven recovered files.

### CEEW daily-aggregate forecasting pilot

A separate pilot used the two uploaded daily aggregate files (28,119 Bareilly and 16,491 Mathura readings), 4 clients, 3 rounds, 3 local epochs and two client-assignment seeds. Each run produced 6,837 chronological test examples.

| Test predictor | MAE (kWh) | RMSE (kWh) | WAPE |
|---|---:|---:|---:|
| Persistence | 1.979 | 3.863 | 0.221 |
| Local-only (mean across two runs) | 3.221 | 5.779 | 0.360 |
| Centralized | 3.243 | 5.846 | 0.362 |
| FedAvg (mean across two runs) | 3.256 | 5.865 | 0.364 |
| Trimmed Mean (mean across two runs) | 3.264 | 5.879 | 0.365 |

Persistence again outperformed the current linear forecasting approaches. This is a useful negative result and a clear model-improvement target. The daily and high-frequency experiments are separate because they use different sampling intervals and must not be mixed into a single forecasting task.

## Post-integration verification

- Full automated suite after SGCC/CEEW integration: **132 passed**.
- Python syntax validation: **90 Python files passed**.
- Dashboard JavaScript `node --check`: passed.
- SGCC benchmark JSON, SGCC federated JSON, CEEW full-ingestion manifest and both CEEW forecasting reports parsed successfully; all numeric values were finite.
- The uploaded SGCC raw CSV was checksum-verified and its label counts match the published SGCC benchmark descriptions.
- CEEW recovery: seven complete CSV members passed CRC32 checks; one incomplete member was excluded.


## CEEW MH2021 re-upload integration — 2026-11-01

The previously truncated `SM Cleaned Data MH2021.csv` was re-uploaded separately and passed complete-file ingestion. Its SHA-256 is `1a0cdf746fe85b55a135b2a13a48f1cc0d7d5046db534f76ba0c6a80846249ab`. It contains **550,560 rows**, **35 Mathura meters**, and spans **2021-01-01T00:00:00** to **2021-02-20T23:57:00**. The dominant sampling interval is 180 seconds. All 550,560 timestamps parsed; the audited numeric columns have zero missing/invalid/negative values. The ingestion checks found no within-chunk or adjacent-chunk-boundary duplicate meter-timestamp keys (this is not a global database-level deduplication proof). Zero consumption occurs in 114,476 rows and is retained as a genuine source value, not converted to missing.

This file contributes **550,560 additional rows** to the seven-file CEEW audit. Across all eight sources, the total is **21,439,039 rows**. Distinct meter unions after combining the sources are Bareilly **46** and Mathura **38**. The eight source files are available in the separate recovered CEEW archive. The project ZIP contains the newly uploaded raw MH2021 file and its normalized gzip version, along with the combined manifest.

### MH2021-only forecasting evaluation

A separate meter-disjoint chronological experiment used all 550,560 source readings, producing 548,192 next-reading examples across 35 meters (328,902 train, 109,638 validation, 109,652 test). Configuration: 4 clients, 2 federated rounds, 1 local epoch, three client-allocation seeds (11, 23, 37). The 95% t intervals describe allocation sensitivity only; they are not population-sampling confidence intervals.

| Predictor | Test MAE (kWh) | Test RMSE (kWh) | WAPE |
|---|---:|---:|---:|
| persistence | 0.002568 | 0.008611 | 0.373 |
| fedavg | 0.006723 | 0.013864 | 0.976 |
| centralized | 0.006723 | 0.013864 | 0.976 |
| trimmed_mean | 0.006726 | 0.013867 | 0.977 |
| local_only | 0.006724 | 0.013861 | 0.976 |

Persistence outperformed FedAvg on this file: MAE was 0.002568 kWh versus 0.006723 kWh. This remains a **consumption forecasting** experiment, not theft detection. The repeated seed runs use the same per-meter chronological split; they should not be interpreted as three independent dataset replications.
