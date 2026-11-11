# Final research implementation and validation report — 2026-11-01

## Scope and integrity statement

This release adds reproducible synthetic research experiments and evaluation tooling. It does **not** manufacture utility inspection labels or claim that synthetic metrics are real-world theft-detection accuracy. No independently verified SGCC/utility inspection CSV was present in the supplied archive. No raw CEEW source CSV was present in this archive either; the CEEW pipeline was exercised with a clearly marked synthetic schema fixture only.

## Changes in this update

1. Added deterministic partial client participation to the federated experiment runner (`client_participation`), with a minimum of three participating clients per round for meaningful robust-aggregation tests. Participation is simulated sampling, not network-level dropout.
2. Exposed the HATTA trust/trimmed-mean blend coefficient as `hatta_trust_weight` and validated its range.
3. Corrected Multi-Krum's Byzantine count to use malicious clients active in the current round.
4. Expanded `scripts/run_fl_comparison.py` summaries to include the centralized reference, DP-FedAvg, and per-client local-only baseline summaries, in addition to FedAvg, FedProx, Trimmed Mean, Multi-Krum, trust-weighted aggregation and HATTA.
5. Added `scripts/run_sensitivity_analysis.py` for one-factor-at-a-time sweeps over malicious-client fraction, trust threshold multiplier, trimmed-mean fraction, local epochs, client participation, HATTA blend weight and benign covariate shift.
6. Added `scripts/run_privacy_utility.py` to generate a client-level Gaussian DP-FedAvg privacy/utility curve across six noise multipliers, five seeds and a full-participation RDP accountant.
7. Added `scripts/evaluate_generalization.py` for leave-one-location-out, season-held-out and chronological temporal evaluation on genuinely labelled meter data.
8. Added regression tests for partial client participation, HATTA blend validation, and cross-location/seasonal/temporal evaluation.

## Verification results

### Automated and runtime checks

- Full pytest suite: **128 passed**.
- Python AST syntax validation: **83 Python files passed**.
- Dashboard JavaScript syntax: `node --check` passed for all dashboard JavaScript files.
- API runtime smoke: Uvicorn started and `/health` returned HTTP 200 with `status=ok`.
- CEEW ingestion/forecast pipeline: synthetic daily-schema fixture processed; 1 normalized file and 2 forecast seed runs completed. Output explicitly says no verified theft labels.
- Cross-location/seasonal/temporal evaluator: synthetic fixture completed for 3 locations, all 4 seasons and a chronological split.
- ZIP archive integrity: checked during packaging.

### Five-seed FL baseline benchmark

Command: `python scripts/run_fl_comparison.py --seeds 11,23,37,53,71 --clients 8 --rounds 5 --samples 1200`

This generated 40 runs: 2 partition conditions × 4 trust-evidence modes × 5 seeds. The table below is the `utility` evidence ablation's mean test metrics on generated synthetic data.

| Partition | Method | Accuracy | F1 | PR-AUC | False-positive rate |
|---|---|---:|---:|---:|---:|
| IID benign | Centralized | 0.912 | 0.460 | 0.669 | 0.003 |
| IID benign | FedAvg | 0.898 | 0.343 | 0.595 | 0.009 |
| IID benign | DP-FedAvg | 0.565 | 0.254 | 0.226 | 0.440 |
| IID benign | Trimmed Mean | 0.901 | 0.357 | 0.587 | 0.007 |
| IID benign | Multi-Krum | 0.902 | 0.374 | 0.580 | 0.008 |
| IID benign | Trust-weighted | 0.898 | 0.343 | 0.595 | 0.009 |
| IID benign | HATTA | 0.900 | 0.355 | 0.595 | 0.008 |
| Severe non-IID benign | Centralized | 0.912 | 0.460 | 0.669 | 0.003 |
| Severe non-IID benign | FedAvg | 0.882 | 0.095 | 0.621 | 0.000 |
| Severe non-IID benign | DP-FedAvg | 0.567 | 0.255 | 0.228 | 0.438 |
| Severe non-IID benign | Trimmed Mean | 0.802 | 0.409 | 0.560 | 0.155 |
| Severe non-IID benign | Multi-Krum | 0.694 | 0.371 | 0.457 | 0.293 |
| Severe non-IID benign | Trust-weighted | 0.880 | 0.057 | 0.622 | 0.000 |
| Severe non-IID benign | HATTA | 0.887 | 0.168 | 0.613 | 0.000 |

**Interpretation:** accuracy alone is misleading under class imbalance. HATTA does not beat Trimmed Mean on the severe non-IID synthetic condition (F1 0.168 vs 0.409). The proposed method's superiority is therefore **not established**. The low DP-FedAvg F1 and high false-positive rate show a substantial privacy/utility cost at the configured noise settings.

### Attack robustness benchmark

Command: `python scripts/run_robustness_suite.py --seeds 11,23,37 --clients 6 --rounds 4 --samples 900`

30 synthetic runs covered benign IID/non-IID conditions and eight attack families. Mean client detection recall / honest-client false-accusation rate:

| Scenario | Detection recall | Honest-client false-accusation rate |
|---|---:|---:|
| IID benign | 0.000 | 0.000 |
| Severe non-IID benign | 0.000 | 0.278 |
| Label flip | 1.000 | 0.133 |
| Scaling | 0.667 | 0.200 |
| Sign flip | 1.000 | 0.133 |
| Backdoor | 0.667 | 0.267 |
| Gaussian update noise | 1.000 | 0.133 |
| Collusion | 1.000 | 0.133 |
| Model replacement | 1.000 | 0.133 |
| Stale update | 0.667 | 0.200 |

**Interpretation:** detection has material false accusations under severe non-IID benign conditions and misses some scaling, backdoor and stale-update attackers. This is an unresolved research limitation, not a result to hide.

### Sensitivity analysis

Command: `python scripts/run_sensitivity_analysis.py --seeds 11,23,37 --clients 6 --rounds 3 --samples 600`

63 runs across seven parameter dimensions completed. These are one-factor-at-a-time synthetic sweeps; they do not measure parameter interactions or real utility populations.

### Differential privacy utility curve

Command: `python scripts/run_privacy_utility.py --seeds 11,23,37,53,71 --clients 8 --rounds 5 --samples 1200 --partition severe`

30 runs completed. Full-participation RDP epsilon (delta=1e-5) and DP-FedAvg mean F1:

| Noise multiplier | Epsilon | DP-FedAvg F1 |
|---:|---:|---:|
| 0.50 | 31.513 | 0.219 |
| 0.75 | 19.090 | 0.214 |
| 1.00 | 13.256 | 0.217 |
| 1.50 | 8.282 | 0.209 |
| 2.00 | 6.003 | 0.208 |
| 3.00 | 3.867 | 0.206 |

This accountant covers the configured client-update Gaussian releases under replacement adjacency and stated clipping assumptions. It does not certify every API, log, model artifact, dashboard export or raw-data release. DP-HATTA is intentionally not claimed because trust weights are derived from update-validation evidence and are not covered by this current DP proof.

### CEEW and generalization smoke tests

- CEEW smoke test used 420 generated daily records for six fixture meters; it verifies the pipeline mechanics only, not the actual CEEW dataset.
- Cross-location/seasonal smoke test used generated labels across three fixture locations and a full year. It verifies split/evaluation mechanics only.
- Neither smoke test may be cited as real-world theft evidence.

## Remaining external / research gates

1. **Real theft-labelled data:** supply an authorised inspection-labelled dataset with independent provenance, label definitions, inspection/adjudication process, data-use permission and checksum. The software can then run `scripts/evaluate_verified_theft.py` and `scripts/evaluate_generalization.py`. Metadata supplied by a user is not independently proven by the software.
2. **HATTA research validity:** current benchmark does not establish HATTA superiority; improve the method only through a pre-registered, leakage-free protocol and rerun all baselines/ablations.
3. **Production secure aggregation:** current pairwise-mask implementation is a research reference. It lacks authenticated key agreement, dropout recovery, malicious-coordinator handling, robust collusion protocol, distributed key erasure and independent cryptographic audit. Do not deploy it as production security.
4. **Application-wide DP:** current accountant covers a specific client-update release, not all outputs. A formal privacy inventory and independent review remain necessary.
5. **Production infrastructure:** PostgreSQL/Redis compose services and queue adapters exist, but business stores are not all migrated from SQLite; no live credentials, failover, backup restore, multi-worker stress test or cloud deployment was supplied.
6. **Security and dashboard QA:** automated API tests and health smoke pass, but external penetration testing, TLS/reverse-proxy review, browser-driven dashboard E2E/visual QA and secret-rotation drills remain outstanding.
7. **Real network dropout:** client participation is simulated via seeded sampling; it is not an asynchronous distributed-client/network failure test.

## Reproducibility commands

```bash
pip install -r requirements.txt
pip install -r requirements-test.txt
python -m pytest -q
python scripts/run_fl_comparison.py --seeds 11,23,37,53,71 --clients 8 --rounds 5 --samples 1200
python scripts/run_robustness_suite.py --seeds 11,23,37 --clients 6 --rounds 4 --samples 900
python scripts/run_sensitivity_analysis.py --seeds 11,23,37 --clients 6 --rounds 3 --samples 600
python scripts/run_privacy_utility.py --seeds 11,23,37,53,71 --clients 8 --rounds 5 --samples 1200 --partition severe
python scripts/evaluate_verified_theft.py --input /path/to/inspection_labelled.csv --provenance /path/to/provenance.json
python scripts/evaluate_generalization.py --input /path/to/inspection_labelled.csv --seeds 11,23,37,53,71
```

All generated reports are stored under `reports/research_runs/`. Keep synthetic reports clearly identified as synthetic and never present them as measured utility performance.
