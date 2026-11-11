# Research contributions and implementation boundaries

## Contribution 1 — Adaptive and calibrated client trust
- Validation-utility, update-integrity, temporal-consistency and heterogeneity evidence.
- Robust validation thresholding and cross-scenario leave-one-attack-family-out calibration in the robustness framework.
- Multi-round suspicion persistence before flagging/down-weighting.
- Gradual trust recovery and client participation support.
- Experimental low-and-slow and adaptive-mimic attacks for stress testing.

## Contribution 2 — Robust aggregation
- FedAvg, FedProx, coordinate trimmed mean, Multi-Krum, trust-weighted aggregation and hybrid HATTA.
- Simulated label flipping, scaling/sign, Gaussian noise, collusion, model replacement, stale updates, backdoor, low-and-slow and adaptive mimic.
- Results must be compared against benign non-IID baselines and reported per attack family. No universal Byzantine guarantee is claimed.

## Contribution 3 — Privacy-aware trust evidence
- Gaussian mechanism for clipped client updates and basic additive RDP accounting.
- Separate optional Gaussian noise for a bounded three-component trust-evidence vector.
- Full-participation accountant intentionally takes no client-subsampling amplification.
- Scope is narrow: this is not end-to-end DP for all model, coordinator, dashboard, logs, checkpoints or raw data. Secure aggregation remains a protocol simulation, not audited cryptography.

## Contribution 4 — Generalisation and efficiency
- Customer-disjoint train/validation/test splits for the supervised SGCC benchmark.
- Temporal feature engineering without label-derived predictors.
- Multiple seeds, PR-AUC, F1, recall, precision, balanced accuracy, FPR, MCC and confidence intervals.
- CEEW forecasting kept separate from theft classification.
- Local workstation CPU, latency, traced-memory and serialized-model-size proxy; no physical edge hardware claim.
