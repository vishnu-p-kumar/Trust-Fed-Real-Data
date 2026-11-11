# Dataset sources, loader, and acquisition notes

## Supplied CEEW Mathura/Bareilly data

The supplied local CEEW files are catalogued and profiled in [DATASET_CARD.md](DATASET_CARD.md). The Harvard Dataverse record is [DOI 10.7910/DVN/GOCHJH](https://doi.org/10.7910/DVN/GOCHJH), version 2, and its metadata lists CC0 1.0. No theft labels are present; the dataset supports consumption, forecasting, supply-quality, heterogeneity, and unlabeled anomaly tasks only.

Use the chunked ingestion CLI to profile or normalize files without editing code:

```powershell
python scripts/prepare_ceew_dataset.py --profile-only --output reports/research_runs/ceew_profile --input "C:\path\to\source.csv" "C:\path\to\another.csv"
python scripts/prepare_ceew_dataset.py --output data/processed/ceew --input "C:\path\to\SM Cleaned Data BR Aggregated.csv" "C:\path\to\SM Cleaned Data MH Aggregated.csv"
```

For the daily aggregate mode, the resulting meter-disjoint federated consumption forecast is:

```powershell
python scripts/run_ceew_forecast.py --input "data/processed/ceew/daily_aggregate/SM Cleaned Data BR Aggregated.normalized.csv.gz" "data/processed/ceew/daily_aggregate/SM Cleaned Data MH Aggregated.normalized.csv.gz" --interval 1D --clients 4 --rounds 3 --local-epochs 5 --learning-rate-candidates 0.01 0.03 0.05 0.1 --seeds 42 43 44 45 46 --output reports/research_runs/ceew_forecast.json
```

For an explicit geographic non-IID partition (one client per city), use `--client-partition location --clients 2 --seed 42` and write to a separate output path. This is a two-client pilot and should not be interpreted as repeated-seed evidence.

Hyperparameters are selected by validation FedAvg MAE. The test set remains chronological and is evaluated after selection. High-frequency source files are too large for the current in-memory forecast runner; use chunked ingestion and a future streaming feature/training implementation for full-resolution learning.

- **SGCC theft detection:** the upstream [dataset repository](https://github.com/henryRDlab/ElectricityTheftDetection) states 42,372 customers over 1,035 days (2014-01-01 to 2016-10-31), provides three multipart archive files, and asks users to cite Zheng et al. (2018). Its displayed repository file listing contains no explicit dataset license, so public availability must not be treated as an unrestricted redistribution license. Confirm the terms for the copy you acquire; this project does not download or redistribute it. Published descriptions report 3,615 abnormal/theft-labeled consumers, while label interpretation and preprocessing should be checked against the selected source version ([Bohani et al., 2021](https://onlinelibrary.wiley.com/doi/10.1155/2021/9136206)).
- **Low Carbon London:** the [UK National Data Library](https://www.data.gov.uk/dataset/df8e55d4-c6d0-498e-abd8-f4c678766cbe/smartmeter-energy-consumption-data-in-london-households1) lists 5,567 households with half-hourly consumption. A filtered 2013 release is available via [TU Delft / 4TU ResearchData](https://research.tudelft.nl/en/datasets/low-carbon-london-smart-meter-data-refactored/) with DOI `10.4121/FBBE775B-48D8-469F-A39B-B64488BFD6FD`. It has no theft ground-truth labels.
- **GoiEner:** Spanish household smart-meter data and metadata are available from [Zenodo record 7859413](https://zenodo.org/records/7859413), with a dataset paper in [Scientific Data](https://www.nature.com/articles/s41597-023-02846-0). It is consumption data, not a theft-labeled benchmark.

Consumption-only datasets can support client heterogeneity, forecasting, anomaly, or transfer studies. Synthetic attack injection into them must be reported as simulated attacks, never as real theft labels.

## SGCC loader and experiment command

`src/federated/datasets.py::load_sgcc_csv` loads an already acquired wide CSV with one meter per row, a unique meter ID (`CONS_NO`, `meter_id`, or supported equivalent), daily columns whose headers parse as dates, and binary labels in the same file (`FLAG`/`is_theft`) or a separate ID/label CSV. It sorts and canonicalizes date columns, preserves missing readings as `NaN`, validates meter uniqueness and labels, computes SHA-256 hashes, and can write a provenance manifest. It does not fetch data or silently substitute synthetic samples.

The upstream instructions say to download `data.zip`, `data.z01`, and `data.z02` together and extract them together. After acquiring an authorized copy and confirming its terms, place the extracted CSV outside version control and run:

```powershell
python scripts/run_sgcc_experiment.py --csv data/raw/sgcc/data.csv --output reports/research_runs/sgcc
```

For a separate labels file, add `--labels data/raw/sgcc/labels.csv`. For integrity verification, pass `--expected-sha256 <sha256>`. Missing paths and invalid schemas fail loudly. The loader returns a provenance manifest with data/label hashes, dimensions, dates, class counts, missingness, preprocessing, citation, and a license caveat. The experiment uses meter-group test and validation splits for `meter_id`; scaling is fit only on the training groups. The dataset is not included in this repository; no real SGCC theft-classification result is claimed until a local authorized CSV is supplied and the experiment completes.
