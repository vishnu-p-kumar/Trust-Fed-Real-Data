# Research upgrade and validation report — 1 November 2026

## Scope

This release advances the four proposed contributions:
1. Adaptive and calibrated client trust estimation.
2. Robust aggregation under adaptive and colluding simulated adversaries.
3. Privacy-aware trust-evidence processing with an explicit Gaussian/RDP accountant.
4. Generalisation, communication and workstation edge-efficiency reporting.

The work is a research prototype. It is not a certified utility deployment or a formal security audit.

## 1. SGCC supervised detection benchmark

Dataset: 10,000 unique customers, 46 engineered predictors, SGCC `FLAG` labels. Five independent customer-disjoint seeds. The outer test set remains untouched by model and threshold selection. Each outer training set is split again by customer into fit and validation groups. Models and decision thresholds are selected using validation PR-AUC/F1 only.

| Metric | Previous Random Forest benchmark mean | Tuned/calibrated release mean |
|---|---:|---:|
| Accuracy | 0.9102 | 0.8831 |
| Precision | 0.4522 | 0.3415 |
| Recall | 0.2816 | 0.3757 |
| F1 | 0.3469 | 0.3475 |
| PR-AUC / Average Precision | 0.3465 | 0.3076 |

The calibrated operating point raises recall and slightly raises F1, while accuracy and PR-AUC are lower than the earlier Random Forest benchmark. These metrics cannot all be improved simultaneously by threshold adjustment. The fixed-0.5 and calibrated results are both retained in `sgcc_tuned_customer_benchmark.json`; the threshold is chosen on validation data only. No test-set threshold tuning is performed.

The benchmark remains class-imbalanced. Accuracy alone is not an adequate success metric. Compare precision, recall, F1, PR-AUC, balanced accuracy, FPR and MCC.

## 2. Federated adversarial evaluation

The SGCC adversarial suite completed 14 runs across 7 attack scenarios and two seeds, on a stratified 2,500-customer computational sample. Scenarios include benign, label-flip, sign-flip, collusion, Gaussian, low-and-slow and adaptive-mimic attacks. This is simulated poisoning of federated client updates, not evidence that these attacks occurred in the utility dataset.

A separate synthetic robustness suite completed 24 runs over 12 scenarios, including severe non-IID partitions and multiple attack families. Results are stored in `robustness_suite.json` and `sgcc_adversarial_suite.json`.

Adaptive attack primitives added:
- Low-and-slow perturbation with bounded relative magnitude.
- Adaptive mimic update that blends a current update with a previous direction.
- Multi-round suspicion persistence before trust down-weighting (`trust_bad_round_patience`).
These mechanisms are experimental. They do not prove detection of arbitrary adaptive adversaries; the adversarial results must be reported scenario by scenario.

## 3. Privacy-aware trust evidence

The privacy/utility pilot completed 12 DP-FedAvg runs and 12 separately noised trust-evidence runs across six Gaussian noise multipliers and two seeds.

The trust-evidence option noises a bounded three-component utility/integrity/temporal vector and reports full-participation Gaussian RDP composition without subsampling amplification. It does **not** make the whole HATTA training pipeline end-to-end differentially private: raw updates and validation-derived harms are still visible to the coordinator. DP-FedAvg and DP trust-evidence are separately reported. Do not combine their epsilon values or claim a whole-application privacy guarantee.

## 4. Generalisation, explainability and edge proxy

- Added temporal profile features: daily change statistics, lag-1/lag-7 autocorrelation, weekday/weekend means, interquartile range and exceedance rate. Feature computation does not use labels.
- Added validation-only permutation importance. Top reported features are in `sgcc_permutation_explanations.json`; these are model reliance indicators, not causal explanations.
- Edge proxy completed on 2,499 sampled customers. Results are in `edge_efficiency_benchmark.json`. This measures a local workstation, not a physical meter or embedded edge device.
- Communication volume is recorded in the federated experiment outputs. No live network or radio transmission was measured.

## 5. Dataset limitations and provenance

- SGCC is historical daily data from a Chinese utility, 2014-01-01 through 2016-10-31. It is not Indian utility data, not live data, and the uploaded archive does not contain individual inspection/audit records.
- CEEW data is treated as consumption/forecasting data only; it has no theft ground-truth labels in the supplied files. Do not use it to claim supervised theft detection.
- The uploaded CEEW archive was damaged. Seven complete CSVs were recovered with CRC checks; the incomplete `SM Cleaned Data MH2021.csv` was excluded. Re-upload that file separately to include it.
- Check the original dataset redistribution terms before redistributing the SGCC raw CSV.

## 6. Reproduction commands

```bash
python scripts/prepare_sgcc_dataset.py --input datasets/sgcc/raw/sgcc_data.csv
python scripts/evaluate_theft_models_tuned.py --seeds 11,23,37,53,71
python scripts/run_sgcc_adversarial_suite.py --seeds 11,23,37
python scripts/run_robustness_suite.py --seeds 11,23,37
python scripts/run_privacy_utility.py --seeds 11,23,37,53,71
python scripts/benchmark_edge_efficiency.py
python scripts/explain_sgcc_model.py
pytest -q
```

## 7. Validation status

The full project test suite passed: **141 tests passed**. Python compilation passed. Additional experiment scripts completed for SGCC tuned detection, 14 SGCC adversarial runs, 24 synthetic robustness runs, 24 privacy utility runs, edge proxy benchmarking and permutation explanations.

A passing test suite establishes software-level checks for the included tests, not correctness of every possible input, production readiness, cryptographic security or external validity.

## 7. PR-AUC and cross-utility extension

A later extension adds `scripts/optimize_sgcc_pr_auc.py` and `scripts/evaluate_ceew_domain_shift.py`.

The SGCC PR-AUC experiment uses the full 42,372-customer table and 46 engineered predictors. Three customer-disjoint outer seeds (11, 23, 37) were completed. Model family is selected on validation Average Precision (balanced ExtraTrees vs. balanced HistGradientBoosting); the decision threshold is calibrated on validation to maximise F1 subject to recall >= 0.40. Mean untouched-test results:

| Metric | Fixed 0.50 threshold | Validation-calibrated threshold |
|---|---:|---:|
| Accuracy | 0.8310 | 0.8975 |
| Precision | 0.3618 | 0.4016 |
| Recall | 0.5165 | 0.4229 |
| F1 | 0.3382 | 0.4110 |
| PR-AUC | 0.3875 | 0.3875 |
| ROC-AUC | 0.8061 | 0.8061 |
| FPR | 0.1396 | 0.0587 |

PR-AUC is identical across the two thresholds because threshold selection cannot change ranking quality. The recall-constrained point retains recall above the requested floor on average while improving precision/F1 and reducing false positives. The 3-seed interval estimates are wide; use more seeds for publication. The previous 0.3076 PR-AUC run used a 10,000-customer sample and a different experiment, so it is not a paired comparison and must not be presented as a statistically verified improvement.

The CEEW domain-shift audit compares 12 common meter-profile features for 38 Mathura and 46 Bareilly meters against SGCC. It reports Wasserstein distances and PSI in `reports/research_runs/ceew_cross_utility_shift.json`. CEEW has no verified theft labels; this is a cross-utility feature-shift audit, not supervised PR-AUC validation.

An optional TDD2022 download/evaluation pathway is included. TDD2022 uses OEDI consumption profiles with six synthetic theft transformations, so it is an independent-source synthetic benchmark rather than independently verified theft ground truth. See `docs/PR_AUC_AND_CROSS_UTILITY_UPGRADE_2026-11-01.md`.

The expanded test suite passes: **146 tests passed**. `python -m compileall -q scripts src tests` also passes.
