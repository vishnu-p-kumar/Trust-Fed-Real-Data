# Experiments

## Quick simulation

From the repository root:

```powershell
python -c "from src.federated.experiment import run_experiment; print(run_experiment({'samples': 400, 'features': 10, 'clients': 4, 'rounds': 3, 'local_epochs': 2, 'partition': 'severe', 'attack': 'sign', 'seed': 42}, output_dir='reports/research_runs/smoke'))"
```

For artifact output and custom configuration, call `run_experiment(config, output_dir=...)` from Python. The FastAPI dashboard provides a bounded default experiment at Federated Research; API parameters allow seed, clients, rounds, local epochs, partition, attack type, attacker fraction, and intensity.

The default fixture is generated with scikit-learn and is **not electricity data**. Do not use its scores as electricity-theft benchmark results. The runner accepts a dataframe with `is_theft`; if `meter_id` is supplied, it uses a customer-group held-out test split. For a trustworthy time-specific benchmark, add an explicit chronological split and ensure feature construction is past-only.

The runner reports accuracy, precision, recall, F1, macro-F1, PR-AUC, ROC-AUC, FPR, confusion matrices, per-client local-only metrics, client participation, trust history, training seconds, communication bytes, and rounds. It saves `config.json`, `results.json`, `rounds.jsonl`, and `checkpoints.npz`. `attack_success_rate` remains null because a targeted backdoor attack is not implemented; controlled sweeps report paired PR-AUC poisoning impact instead.

## Calibrated trust study

`run_calibrated_study` covers benign IID/moderate/severe data, sign flips at multiple malicious fractions, scaling strengths/fractions and clipping bounds, label flips, benign covariate shifts, and temporary sign attacks. It compares utility, integrity, temporal, and heterogeneity-adjusted evidence; FedAvg, trimmed mean, trust-only, and HATTA; and recovery settings. For each evaluation scenario, calibration excludes that entire attack family and uses a disjoint seed set. It reports precision, recall, honest-client false accusation rate, global and per-client metrics, standard deviations, 95% t intervals, paired PR-AUC impact, and recovery trust. The results are exploratory synthetic evidence; targeted attack success is undefined. The report artifact is `reports/research_runs/trust_validation_20261028.json`; see [TRUST_VALIDATION.md](TRUST_VALIDATION.md).

Reproduce the documented seed set from the repository root:

```powershell
python scripts/run_trust_validation.py
```

Pass `--calibration-seeds` and `--evaluation-seeds` as separate integer lists to use another non-overlapping seed set. The script rejects overlapping sets through the study runner.

The default run uses five calibration and five disjoint evaluation seeds, with 400 synthetic rows, 10 features, four clients, three rounds, and two local epochs. It also contains IID/moderate/severe partition conditions. The client-feature shift and poisoning attacks are controlled simulations, not real utility data or observed intrusions. `attack_success_rate` remains null because no targeted backdoor objective exists.

Suggested paper protocol: public customer-disjoint and chronological evaluation, larger client counts, more than five repeats, confidence intervals, PR-AUC and recall at fixed FPR, attack cessation/recovery, broader benign shifts, and utility/privacy ablations. Keep final test sets untouched by threshold, trust, and model selection.

## Public data

SGCC is commonly used as theft-labeled customer consumption data. Record exact source/version, license, labels, missingness, and preprocessing. Low Carbon London and GoiEner are consumption datasets without theft labels; they can support non-IID distribution or transfer studies, not real theft-label claims. Obtain source data independently and follow the acquisition conditions.
