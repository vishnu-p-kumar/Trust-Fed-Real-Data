# Uploaded dataset addendum — 2026-11-01

This addendum supersedes data-availability statements in the original pre-upload validation reports.

The user subsequently supplied:
1. SGCC Electricity Theft Detection benchmark: 42,372 customers, 3,615 FLAG=1 and 38,757 FLAG=0; 1,034 daily consumption columns; customer-disjoint five-seed benchmark and three-seed federated pilot completed.
2. CEEW Mathura/Bareilly smart-meter data: seven complete CSV members recovered from a truncated archive and CRC-verified, followed by a separate complete re-upload of `SM Cleaned Data MH2021.csv`; eight sources and 21,439,039 readings are now ingested across 46 Bareilly and 38 Mathura meters.

Current results and limitations are in `UPLOADED_DATASET_EVALUATION_2026-11-01.md`. Earlier synthetic experiment results remain synthetic and must not be described as real-world results. CEEW has no theft labels and is used only for forecasting/consumption analysis. SGCC is a historical China utility benchmark, not a live feed or Indian utility validation.


The re-uploaded MH2021 file adds 550,560 three-minute readings from 35 Mathura meters (2021-01-01 to 2021-02-20). Its separate three-seed forecast evaluation is in `reports/research_runs/ceew_mh2021_forecast.json`; persistence remains the strongest baseline.
