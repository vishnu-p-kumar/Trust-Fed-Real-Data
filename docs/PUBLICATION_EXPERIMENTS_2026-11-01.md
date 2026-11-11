# Publication-oriented experiment results — 2026-11-01

## Implemented changes

- Adaptive trust now uses measured validation contribution utility, pre-clipping update norm/integrity and temporal cosine consistency. The non-flagged recovery path no longer hard-codes utility to 1.0.
- HATTA combines trust-weighted clipped updates with coordinate trimmed mean.
- Attack simulation includes label flipping, sign/update scaling, Gaussian update noise, collusion, model replacement, stale updates and backdoor poisoning.
- The privacy baseline applies client-update L2 clipping and Gaussian noise to the mean, with full-participation RDP composition and no subsampling amplification.
- A new SGCC adversarial runner evaluates the proposed methods on a deterministic, stratified customer subset with customer-disjoint train/validation/test partitions.

See `ADAPTIVE_TRUST_AWARE_RESEARCH_METHOD.md` for equations, threat-model scope and privacy limitations.

## Executed experiments

| Experiment | Executed configuration | Result artifact |
|---|---|---|
| Synthetic robustness | 10 scenarios × 3 seeds = 30 runs; 6 clients; 4 rounds; 900 samples | `reports/research_runs/publication_robustness_2026-11-01.json` |
| Synthetic privacy/utility | 6 noise multipliers × 3 seeds = 18 runs; 6 clients; 5 rounds; 900 samples | `reports/research_runs/publication_privacy_utility_2026-11-01.json` |
| SGCC adversarial pilot | 5 scenarios × 3 seeds = 15 runs; 5,000 stratified customers; 6 clients; 2 rounds | `reports/research_runs/sgcc_adversarial_suite_2026-11-01.json` |
| Existing SGCC supervised benchmark | 5-seed customer-disjoint benchmark | `reports/research_runs/sgcc_customer_disjoint_benchmark.json` |
| Existing SGCC federated benign pilot | 3-seed exploratory run | `reports/research_runs/sgcc_federated_multiseed.json` |

## Measured findings

### Synthetic robustness

HATTA F1 exceeded FedAvg F1 in the executed severe non-IID scenarios, for example:

| Scenario | FedAvg F1 | HATTA F1 |
|---|---:|---:|
| Severe non-IID, benign | 0.300 | 0.446 |
| Label flipping | 0.197 | 0.267 |
| Sign attack | 0.197 | 0.285 |
| Collusion | 0.345 | 0.315 |
| Model replacement | 0.428 | 0.391 |
| Stale updates | 0.300 | 0.470 |

HATTA does not win every scenario (including collusion and model replacement in this run). These are controlled synthetic experiments and the results do not establish general robustness against adaptive adversaries.

### SGCC-labelled adversarial pilot

The 5,000-customer stratified subset contained 4,573 normal and 427 theft-labelled customers. Across three seeds, HATTA F1 was:

| Scenario | FedAvg F1 | HATTA F1 |
|---|---:|---:|
| Benign | 0.155 | 0.191 |
| Label flipping | 0.169 | 0.189 |
| Sign flipping | 0.152 | 0.189 |
| Collusion | 0.147 | 0.205 |
| Gaussian update noise | 0.147 | 0.206 |

The client-detection signal remains weak: mean honest false-accusation rate was approximately 27.8% in the benign scenario and 20.0% in the attacked scenarios; mean detection precision in attacked scenarios was 0.50. Therefore, the current client-flagging mechanism is not sufficiently reliable for enforcement or for a strong attacker-identification claim. This pilot uses simulated attacks and only a stratified 5,000-customer subset, not the full SGCC cohort.

### Privacy–utility trade-off

The five-round full-participation RDP accountant reported the following mean epsilon values at delta = 1e-5:

| Noise multiplier | Mean epsilon | DP-FedAvg F1 | Non-private FedAvg F1 |
|---:|---:|---:|---:|
| 0.5 | 31.513 | 0.176 | 0.335 |
| 0.75 | 19.090 | 0.168 | 0.335 |
| 1.0 | 13.257 | 0.165 | 0.335 |
| 1.5 | 8.282 | 0.173 | 0.335 |
| 2.0 | 6.003 | 0.172 | 0.335 |
| 3.0 | 3.867 | 0.171 | 0.335 |

This demonstrates a utility cost in the configured synthetic experiment. The reported privacy accounting covers only the Gaussian noisy mean of clipped client updates under replacement adjacency and the stated full-participation assumptions. It does not include validation-derived trust evidence, HATTA, logs, checkpoints, dashboards, raw data or all application outputs. Do not describe the entire application as differentially private.

## Verification

- Focused federated, attack, privacy, and Phase-III tests: 41 passed.
- Full test suite after the trust update: 133 passed.
- Synthetic robustness suite: 30/30 runs completed and JSON output parsed.
- Synthetic privacy/utility suite: 18/18 runs completed and JSON output parsed.
- SGCC adversarial pilot: 15/15 runs completed and JSON output parsed.

The experiment scripts emitted a non-fatal third-party spreadsheet-runtime warmup warning in this environment; the Python experiments exited successfully and wrote their result files.

## Publication gates still outstanding

1. Run a larger, pre-registered SGCC study with more seeds, clients and communication rounds, preferably the full customer cohort once compute is provisioned.
2. Calibrate attacker thresholds on independent attack-family seeds and report held-out honest false-accusation rates; the current SGCC pilot shows this is a key weakness.
3. Add a proper ablation study for trust utility, integrity, temporal consistency, trust decay/recovery and the HATTA blend coefficient.
4. Add independently verified Indian utility theft labels before claiming Indian cross-dataset theft generalisation.
5. Validate the DP adjacency and threat model, and design privacy protection for the validation evidence used by trust scoring before claiming end-to-end DP for HATTA.
6. Benchmark peak memory, client/server hardware, inference latency and actual transmitted payloads. Current timing/byte counters are research estimates, not production deployment measurements.
7. Compare against recent published methods and report confidence intervals and paired statistical tests on predeclared splits.

These results are suitable as an implementation and pilot-evaluation milestone, not as final evidence that the framework is production-ready or publication-accepted.
