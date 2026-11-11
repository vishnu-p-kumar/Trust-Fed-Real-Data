# Dataset-integrated release manifest — 2026-11-01

## Included
- Full uploaded SGCC raw customer-level daily CSV and its processed 37-feature customer table.
- Five-seed customer-disjoint SGCC classification benchmark with confidence intervals.
- Three-seed severe non-IID federated pilot using the raw SGCC profiles.
- Eight-source CEEW dataset package: seven CRC-verified archive recoveries plus the separately re-uploaded MH2021 file; 21,439,039 rows ingested.
- High-frequency, daily aggregate and MH2021-specific CEEW forecasting pilot reports.
- Recovery, preprocessing, ingestion, centralized benchmark and federated benchmark scripts.
- Dataset cards, limitations, source citations and reproducibility instructions.

- Complete raw CEEW source archive is also supplied separately as `CEEW-Recovered-Eight-Complete-Files.zip`.
- MH2021 normalized gzip file, source CSV, and three-seed forecasting report are included in the project ZIP.

## Verification
- Automated test suite: 132 passed.
- Python syntax validation: 90 files passed.
- Dashboard JavaScript syntax checks: passed.
- SGCC and CEEW result JSON files parse and contain finite numeric values, including the new MH2021 forecast.
- CEEW recovered source archive: 8 complete CSV files; the first seven were recovered with CRC32 verification and MH2021 was separately re-uploaded and validated.
- SGCC raw dataset SHA-256 and processed artifact checksums: `RELEASE_CHECKSUMS_2026-11-01.json`.

## Important scope
SGCC is a historical China utility benchmark, not a live feed or Indian utility validation. CEEW is unlabeled for theft and is only used for forecasting/consumption analysis. Both forecasting pilots found persistence outperformed the current linear model. HATTA's SGCC federated pilot does not establish superiority over baselines. Check upstream data terms before redistribution of raw SGCC data.
