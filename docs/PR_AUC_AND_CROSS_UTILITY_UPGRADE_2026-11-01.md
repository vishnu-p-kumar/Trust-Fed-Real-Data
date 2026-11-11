# PR-AUC and cross-utility validation upgrade — 1 November 2026

## Scope and research integrity

This upgrade adds a full-cohort SGCC model-ranking experiment, a recall-constrained operating point, an external TDD2022 benchmark adapter, and a CEEW Mathura/Bareilly feature-shift audit.

The project does **not** claim that all evaluation metrics improved. PR-AUC is a ranking metric and cannot be improved by changing the classification threshold. The threshold is calibrated separately on validation data to target a minimum recall.

## SGCC full-cohort PR-AUC experiment

- Dataset: 42,372 SGCC customers, 46 engineered customer-level predictors.
- Seeds: 11, 23, 37 (three-seed pilot).
- Split: customer-disjoint 80/20 outer holdout; customer-disjoint fit/validation split inside the training partition.
- Candidate families: balanced ExtraTrees and class-weighted HistGradientBoosting.
- Model selection: validation Average Precision (PR-AUC) only.
- Threshold selection: validation-only maximisation of F1 subject to recall >= 0.40.
- The outer test partition is never used for model or threshold selection.

Mean test results across three seeds:

| Metric | Fixed threshold 0.50 | Validation threshold, recall floor 0.40 |
|---|---:|---:|
| Accuracy | 0.8310 | 0.8975 |
| Precision | 0.3618 | 0.4016 |
| Recall | 0.5165 | 0.4229 |
| F1 | 0.3382 | 0.4110 |
| PR-AUC / Average Precision | 0.3875 | 0.3875 |
| ROC-AUC | 0.8061 | 0.8061 |
| False-positive rate | 0.1396 | 0.0587 |

PR-AUC and ROC-AUC are unchanged by threshold calibration, as expected. The recall-constrained operating point improves precision, accuracy, F1 and false-positive rate relative to the fixed 0.50 point, while lowering recall from 0.5165 to 0.4229 but remaining above the 0.40 validation target on average. Individual seed results and confidence intervals are in `reports/research_runs/sgcc_pr_auc_optimisation.json`.

**Comparison caveat:** the earlier 0.3076 PR-AUC result used a 10,000-customer tuning sample and a different model/split experiment. It is not a paired baseline. The new 0.3875 full-cohort result is a stronger current benchmark, but a statistically valid claim of improvement requires rerunning the old baseline on the exact same outer splits. The three-seed confidence intervals are wide for several threshold-dependent metrics; increase the number of seeds before publication.

## Cross-utility CEEW audit

The new script compares the SGCC benchmark's common profile statistics with the CEEW Mathura and Bareilly daily-aggregate cohorts. It uses 38 Mathura meters and 46 Bareilly meters with at least 30 daily observations, comparing 12 profile statistics using Wasserstein distance, quantile ranges and a reference-binned Population Stability Index (PSI).

Results are in `reports/research_runs/ceew_cross_utility_shift.json`.

CEEW files contain no verified theft labels. Consequently, this audit reports **feature-distribution shift only**. It does not report PR-AUC, recall, accuracy, or theft-classification transfer performance. This is an important cross-utility data audit, not a supervised external validation.

## Additional labelled benchmark pathway: TDD2022

The project includes an optional downloader and evaluation adapter for [TDD2022 on Mendeley Data](https://data.mendeley.com/datasets/c3c7329tjj/1), released under CC BY 4.0. TDD2022 combines OEDI consumption profiles with six synthetically generated theft transformations. It provides a separate data source and useful controlled stress test, but its positive labels are **synthetic**, not independently verified utility theft incidents.

Run:

```bash
python scripts/download_tdd2022.py
python scripts/evaluate_tdd2022_external.py --seeds 11,23,37 --target-recall 0.40
```

The adapter holds out entire consumer `Class` groups so the test includes unseen building types. It deliberately reports TDD2022 separately from SGCC. Do not pool their scores or describe TDD2022 labels as field-verified theft.

## Reproduction commands

```bash
python scripts/optimize_sgcc_pr_auc.py --seeds 11,23,37 --target-recall 0.40
python scripts/evaluate_ceew_domain_shift.py
python scripts/download_tdd2022.py  # optional external dataset acquisition
python scripts/evaluate_tdd2022_external.py --seeds 11,23,37 --target-recall 0.40
pytest -q
```

## Remaining research requirement

A truly independent, independently audited theft-labelled dataset from a second utility is still required to establish cross-utility PR-AUC. The supplied CEEW data are unlabelled, while TDD2022 is synthetically labelled. The next defensible step is a utility/academic collaboration that provides meter-level inspection outcomes and a documented label-generation protocol, followed by a frozen external test set and paired confidence intervals.
