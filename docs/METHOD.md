# Trust aggregation candidate

The repository still calls the combined candidate HATTA, but this is a provisional name, not a novelty or superiority claim.

## Validation evidence and decision rule

For each client update, the coordinator measures the increase in binary log loss on an internal validation split: `harm = max(0, loss(global + client_delta) - loss(global))`. The detector does not use client IDs or the simulated malicious-client list. PR-AUC changes are not used as the trust utility signal because a reversed ranking can improve PR-AUC on an imbalanced validation set.

The default per-round threshold is `median(harm) + 2.5 * 1.4826 * MAD(harm)`, with a small numerical floor. In the controlled study, each scenario gets a threshold calibrated on separate seeds and scenario families that exclude the evaluation attack family. The threshold is selected subject to a maximum calibration honest-client false accusation rate. Simulated attacker labels are used only by calibration; neither evaluation seeds nor the same attack family enter that threshold. This is supervised, cross-family simulation calibration, not a deployable unlabeled threshold guarantee.

An update above threshold is downweighted by a harm-dependent factor and recorded as flagged; otherwise trust recovers gradually. Integrity, temporal consistency, and heterogeneity-adjusted validation harm are ablations. The heterogeneity variant reduces an accusation score when class-conditional validation loss changes conflict; this is a candidate signal, not a validated heterogeneity estimator. Update disagreement by itself is not an accusation signal. Coordinator-visible validation data remains a privacy/governance assumption and can still penalize a benign client whose local distribution harms the shared validation objective.

## Aggregation comparisons

- **FedAvg:** sample-count weighted mean of clipped updates.
- **Trimmed mean:** coordinate-wise trimmed mean.
- **Trust-only:** sample-count and current trust weighted mean.
- **HATTA:** equal mixture of trust-only and coordinate trimmed mean.

All methods train from the same client partitions and are evaluated on the same held-out test split for each seed. The experiment is a single-process simulator; raw client records are not serialized to the coordinator but there is no separate process or network privacy boundary.

## Current evidence

See [TRUST_VALIDATION.md](TRUST_VALIDATION.md) and `reports/research_runs/trust_validation_20261028.json`. The latest study uses leave-one-attack-family-out calibration, attack strength/fraction sweeps, multiple non-IID severities, temporary attacks, recovery, and trust-evidence ablations with repeated-seed uncertainty. Synthetic results do not establish real meter performance, robust security, or novelty.
