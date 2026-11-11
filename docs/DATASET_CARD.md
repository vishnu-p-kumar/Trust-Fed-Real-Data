# CEEW Mathura and Bareilly smart-meter dataset card

## Source, citation, and license

The supplied files are from Agrawal, Shalu; Mani, Sunil; Ganesan, Karthik; and Jain, Abhishek, **“High frequency smart meter data from two districts in India (Mathura and Bareilly)”**, Harvard Dataverse, version 2, DOI [10.7910/DVN/GOCHJH](https://doi.org/10.7910/DVN/GOCHJH). The Dataverse record describes three-minute readings from nearly 100 urban households in Mathura and Bareilly, Uttar Pradesh, from May 2019 through October 2021 and identifies the record’s license as [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The supplied README names CEEW and the authors, and describes the project as household electricity supply/use analysis.

Suggested citation: Agrawal, Shalu, Sunil Mani, Karthik Ganesan, and Abhishek Jain. 2021. *High frequency smart meter data from two districts in India (Mathura and Bareilly)*. Harvard Dataverse, V2. https://doi.org/10.7910/DVN/GOCHJH. Related report: Agrawal et al. 2020, *What Smart Meters Can Tell Us? Insights on Electricity Supply and Use in Mathura and Bareilly Households*, Council on Energy, Environment and Water.

The Dataverse record reports CC0 1.0. Keep its citation and version DOI with derived results. The supplied README itself does not state a license; license identification above comes from the Dataverse record, not from that text file.

## Supplied files and inspected structure

The user's Downloads directory contains eight CSV files plus `CEEW -  ReadMe.txt`. They were inspected in place; original files were not changed or copied into the repository. CSV column headers and sample rows were read, then all CSV rows were streamed in chunks for the profile manifest. If raw copies are kept locally, put them under ignored `data/raw/ceew/`; the CLI accepts configurable paths and does not require an absolute location in source code. No meter ID values are listed in this card or in the profile report.

| Supplied CSV | Schema/mode | Rows | Meters in file | Observed timestamp range |
|---|---|---:|---:|---|
| `CEEW - Smart meter data Bareilly 2020.csv` | Three-minute: timestamp, kWh, voltage, current, frequency, meter | 6,627,360 | 46 | 2020-01-01 to 2020-12-31 |
| `CEEW - Smart meter data Bareilly 2021.csv` | Three-minute, same fields | 3,948,960 | 38 | 2021-01-01 to 2021-10-31 |
| `SM Cleaned Data BR2019.csv` | Three-minute, same fields | 2,919,315 | 46 | 2019-05-09 to 2019-12-31 |
| `CEEW - Smart meter data Mathura 2019.csv` | Three-minute, same fields | 3,588,874 | 38 | 2019-05-01 to 2019-12-31 |
| `CEEW - Smart meter data Mathura 2020.csv` | Three-minute, same fields | 3,759,360 | 38 | 2020-01-01 to 2020-12-31 |
| `SM Cleaned Data MH2021.csv` | Three-minute, same fields | 550,560 | 35 | 2021-01-01 to 2021-02-20 |
| `SM Cleaned Data BR Aggregated.csv` | Daily: meter, date, kWh | 28,119 | 46 | 2019-05-09 to 2021-10-31 |
| `SM Cleaned Data MH Aggregated.csv` | Daily: meter, date, kWh | 16,491 | 38 | 2019-05-01 to 2021-02-20 |

The supplied three-minute files total **21,394,429 readings** across six CSVs; the daily aggregate files contain **44,610 rows**. The profile scan found **46 distinct meter IDs in Bareilly** and **38 in Mathura** across the supplied files. The two resolutions overlap and are not independent samples. Do not concatenate daily totals with three-minute observations in one training series. The supplied files do not cover every city/year combination named in the README: Bareilly 2019 is supplied as a cleaned file; Mathura 2021 is supplied only through February 20; there is no full Mathura 2021 three-minute file.

Three-minute headers are `x_Timestamp`, `t_kWh`, `z_Avg Voltage (Volt)`, `z_Avg Current (Amp)`, `y_Freq (Hz)`, and `meter`. Daily headers are `meter`, `Date`, and `t_kWh`. The README describes the high-frequency data as readings at three-minute intervals. Actual files include gaps; the ingestion manifest records observed interval frequencies and time-order issues. Dates parse as local-naive timestamps; the source does not provide a timezone in the supplied README. No timezone conversion is applied.

## Labels and intended use

**No supplied CSV has a verified electricity-theft label.** The fields measure energy use and supply conditions. Abnormal values, zero readings, outages, missing intervals, or forecast residuals are not theft labels. No supervised theft classification, theft precision/recall/F1/AUC, or real-world theft-detection claim may be computed from these files.

Supported exploratory tasks include consumption profiling, demand/next-reading forecasting, supply-quality and client heterogeneity analysis, and unlabeled anomaly triage. An anomaly proxy is only a signal for further investigation; it cannot establish theft. Simulated theft experiments must remain separately named and must never be presented as real CEEW theft detections.

The new federated forecast experiment assigns complete meter groups to clients deterministically, creates past-only lag/calendar features, and splits each meter chronologically into train/validation/test examples. FedAvg and coordinate trimmed mean are compared with centralized, local-only, and persistence baselines. A validation-selected forecast-residual quantile is reported only as an unlabeled anomaly proxy. The classifier trust scoring and HATTA malicious-client metrics remain for the separately labeled synthetic benchmark; they are not measured on CEEW.

## Quality profile and preprocessing

The full source scan uses `src.ceew_dataset.ingest_ceew_files` in 200,000-row chunks and writes only `reports/research_runs/ceew_profile/ceew_manifest.json`. It counts records, distinct meters per file, parseable timestamp range, missing/invalid numeric values, negative consumption/current, zero-consumption records, adjacent/within-chunk duplicate keys, and observed time intervals. It does not impute missing readings, delete duplicates, or emit synthetic labels. Duplicate readings are retained in normalized files and exposed in the quality report. Duplicate counts are within chunks plus adjacent chunk boundaries, not a global database-backed deduplication audit.

In the full scan, the six three-minute files had no missing/invalid numeric entries in the measured fields, no invalid timestamps, no negative energy/electrical readings, and no duplicate keys found. Per-meter timestamps were strictly increasing in source order. About 99.98% of consecutive per-meter steps were exactly 180 seconds; the rest were gaps of other lengths. There were 3,505,437 zero-kWh readings (16.38% of the three-minute rows), plus 1,751,938 zero-voltage, 2,892,849 zero-current, and 1,751,945 zero-frequency observations. Zeros are preserved and may represent genuine zero use, outages, disconnection, or data-quality behavior; the source alone cannot distinguish those explanations. Numeric maxima across the high-frequency files were 0.300 kWh, 654.73 V, 126.05 A, and 570.33 Hz, respectively. The voltage and frequency extremes need review with a domain expert; no arbitrary engineering threshold was applied and no readings were deleted. In daily aggregate files, only meter/date/kWh exist; voltage/current/frequency are absent by design, not missing measured values. Counts and ranges by file and observed intervals are in the manifest.

Normalized data is written under ignored `data/processed/ceew/{high_frequency,daily_aggregate}/` paths, separately from raw inputs. Timestamps are parsed to a canonical timestamp field; numeric fields are coercively parsed, invalids become null and are counted, and every input row is retained. No filling or interpolation occurs. For consumption forecasting, invalid/negative consumption rows and duplicate meter/timestamp keys are excluded from feature construction and counted; the ingestion output itself remains unchanged. Only exact interval links with one-step and seven-day history are used, so irregular gaps reduce forecast examples rather than being filled.

## Reproduction commands

Keep the attached raw files outside version control. From the repository root, pass the actual local paths (or another configured path) to the CLI; source paths are not hardcoded in code:

```powershell
python scripts/prepare_ceew_dataset.py --profile-only --output reports/research_runs/ceew_profile --input "C:\path\to\CEEW - Smart meter data Bareilly 2020.csv" "C:\path\to\CEEW - Smart meter data Mathura 2019.csv"
python scripts/prepare_ceew_dataset.py --output data/processed/ceew --input "C:\path\to\SM Cleaned Data BR Aggregated.csv" "C:\path\to\SM Cleaned Data MH Aggregated.csv"
python scripts/run_ceew_forecast.py --input "data/processed/ceew/daily_aggregate/SM Cleaned Data BR Aggregated.normalized.csv.gz" "data/processed/ceew/daily_aggregate/SM Cleaned Data MH Aggregated.normalized.csv.gz" --interval 1D --clients 4 --rounds 3 --local-epochs 5 --learning-rate-candidates 0.01 0.03 0.05 0.1 --seeds 42 43 44 45 46 --output reports/research_runs/ceew_forecast.json
```

The first command profiles the full input without writing normalized readings. Omit `--profile-only` to write chunked gzip CSVs. `--max-rows-per-file` is for smoke runs and marks the manifest partial. Daily aggregate files are small enough to use in the current in-memory forecasting runner. Do not load all high-frequency files into memory together; a streaming training/feature pipeline is still needed for full-scale three-minute federated training.

## Executed real-data forecast smoke result

The daily aggregate files from both locations were normalized in full and used in a five-seed, four-client, three-round, five-local-epoch forecast run. Seeds 42–46 change meter-to-client assignment only; the same per-meter chronological 60/20/20 split is used for each, so the intervals below quantify client-allocation sensitivity, not population or temporal sampling uncertainty. The learning rate was chosen independently for each run from 0.01, 0.03, 0.05, and 0.1 by validation FedAvg MAE only; 0.1 was selected in every run. Each run had 34,011 regular examples: 20,373 training, 6,801 validation, and 6,837 test examples from 84 meters. No invalid or duplicate keys were excluded during forecast feature building.

| Method | Test MAE mean (95% t interval) | RMSE mean (kWh) | WAPE mean |
|---|---:|---:|---:|
| Centralized linear forecast | 2.1287 [2.1287, 2.1287] | 3.9281 | 0.2377 |
| FedAvg | 2.1330 [2.1301, 2.1358] | 3.9365 | 0.2382 |
| Coordinate trimmed mean | 2.1328 [2.1253, 2.1403] | 3.9342 | 0.2382 |
| Local-only | 2.1282 [2.1196, 2.1367] | 3.9248 | 0.2377 |
| Persistence (previous reading) | 1.9787 [1.9787, 1.9787] | 3.8634 | 0.2210 |

Persistence outperformed the trained methods across these five client-allocation seeds, so the result does not support a claim that FL improves forecasting. Paired test MAE was 0.1542 kWh higher for FedAvg than persistence (95% t interval [0.1513, 0.1571]). The unchanged data split makes some intervals degenerate (zero across-seed variance); these are not generalization intervals. The validation 99th percentile of FedAvg absolute residuals ranged from 14.8104 to 14.8348 kWh; 87 of 6,837 test residuals exceeded it in each run. This is an unlabeled residual proxy only, not a theft or anomaly detection accuracy result. The machine-readable run artifact is `reports/research_runs/ceew_forecast.json`.

A separate **single-seed geographic non-IID pilot** assigned all Bareilly meters to one client and all Mathura meters to another (`--client-partition location --clients 2`). FedAvg test MAE was 2.1311 kWh, trimmed-mean MAE 2.1251 kWh, and persistence MAE 1.9787 kWh. The result does not show an FL gain and has no seed-based uncertainty estimate because only two natural location groups exist. See `reports/research_runs/ceew_forecast_location.json`.

## Reproducibility and limitations

The profile manifest records file names, SHA-256 hashes, row counts, quality counters, time ranges, and preprocessing choices, but not absolute source paths or meter IDs. Results depend on the exact Dataverse version and supplied-file contents; compare hashes before reproducing. The currently tested forecast is a small prototype with linear regression and fixed calendar/log transforms. Its default comparators do not include the classification HATTA trust policy because there are no theft labels and no validated regression trust criterion. It is a proof of data integration, not an optimized forecasting result or theft-detection study.

Remaining research needs include verified theft labels from a separate legitimate source if theft detection is the goal; documenting timestamp timezone and exact meter privacy protections; checking every row for global duplicate keys if needed; evaluating forecast models over multiple temporal cutoffs and seeds; and developing memory-bounded feature generation for the full high-frequency series. The dataset is a purposively selected sample of urban households, not a representative population sample of all Indian consumers.
