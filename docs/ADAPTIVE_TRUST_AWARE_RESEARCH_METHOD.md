# Trust-Fed-Grid-X: Adaptive Trust-Aware Research Method

## Research objective

Evaluate whether adaptive client trust and robust aggregation improve federated electricity-theft detection under non-IID customer distributions and simulated malicious clients, while quantifying the privacy/utility and communication/compute trade-offs.

## Contribution 1 — adaptive trust-aware aggregation

For client \(i\) at round \(t\), the current implementation derives:

- Validation contribution utility from the increase in binary log loss when the client's clipped update is applied to the current global model.
- Update integrity from the pre-clipping L2 norm relative to the configured clipping bound.
- Temporal consistency from cosine similarity with the client's previous update.

The smoothed trust score is:

\[
T_i^{(t)} = \operatorname{clip}_{[0,1]}
\left(0.55T_i^{(t-1)} + 0.25U_i^{(t)}
+0.12I_i^{(t)}+0.08C_i^{(t)}
+\rho\max(0,0.5-T_i^{(t-1)})\right)
\]

where \(U\), \(I\), and \(C\) are utility, integrity and consistency evidence and \(\rho\) is the recovery rate. A detected harmful update is downweighted with an exponential penalty based on its excess validation harm. The round threshold uses a median/MAD robust threshold on training-only validation observations.

Trust-weighted aggregation combines client sample size and trust. HATTA then combines trust-weighted aggregation with coordinate-wise trimmed mean:

\[
\Delta_t^{H} = \lambda \sum_i w_i(T_i,n_i)\Delta_i
+(1-\lambda)\operatorname{TrimmedMean}(\{\Delta_i\})
\]

The trust recovery path now uses the measured contribution utility \(U_i^{(t)}\), rather than assigning every non-flagged client a hard-coded perfect utility value. This prevents a consistently low-utility client from receiving an artificial trust boost solely because it did not cross the current outlier threshold.

### Validation boundary

The validation set is drawn only from the training partition and is separate from the final test set. It is a coordinator-visible validation set in this simulation. This is not a privacy-preserving validation protocol; a deployment must account for the information exposed by validation or use a separately justified privacy-preserving contribution protocol. The test set is not used for trust decisions or threshold selection.

## Contribution 2 — adversarial robustness

Supported controlled attack modes include label flipping, update scaling, sign flipping, slow/sign manipulation, Gaussian update noise, model replacement, stale updates, backdoor poisoning and colluding perturbations. Experiments should vary:

- IID, moderate and severe label-skewed partitions.
- Client counts and malicious-client fractions.
- Attack family and intensity.
- Random seeds and communication rounds.

Compare FedAvg, FedProx, coordinate trimmed mean, Multi-Krum, trust-weighted aggregation and HATTA. Report theft-class precision/recall/F1, PR-AUC, false-positive rate, client-detection precision/recall, honest false-accusation rate and paired degradation against a clean run.

The attack implementations are controlled simulations. They do not prove resilience to every adaptive adversary, and Multi-Krum's assumptions must be checked against the actual client count and Byzantine bound.

## Contribution 3 — privacy and deployment trade-offs

The `fedavg_dp` experimental baseline clips each client update and adds Gaussian noise to the mean. The RDP accountant uses full participation, basic additive composition, and no subsampling amplification. It reports epsilon for the configured number of rounds and delta.

This privacy claim is limited to the configured noisy client-update release under replacement adjacency. It does not cover HATTA's validation-derived trust evidence, application logs, checkpoints, dashboards, raw data or other model releases. It is not a production privacy certification.

Efficiency measurements include training duration, communication bytes, messages, rounds and participation. For a paper, additionally report hardware, software versions, peak memory, inference latency and client/server timing under a documented environment.

## Reproducibility and reporting

- Freeze data preprocessing and customer-level train/validation/test partitions before model comparison.
- Keep test customers disjoint from training customers.
- Use multiple predeclared seeds and report mean, standard deviation and confidence intervals.
- Use validation-only threshold calibration; never tune on the final test set.
- Report class imbalance and PR-AUC alongside accuracy.
- Include ablations for utility-only, integrity, temporal consistency, heterogeneity handling, trust decay/recovery, DP and aggregation components.
- Publish configuration files, dataset hashes, environment versions, result JSON and exact commands.

## Data scope and limitations

The SGCC dataset is the labelled historical theft-detection benchmark. The CEEW Mathura/Bareilly data are unlabeled consumption observations and are used for forecasting/consumption analysis, not supervised theft detection. CEEW cannot be described as independent Indian theft-label validation without utility-confirmed theft labels. Simulated attacks and synthetic fixtures must be identified as simulations, not observed utility attacks.
