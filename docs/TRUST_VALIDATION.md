# Trust based federated learning validation

**Status:** exploratory synthetic simulation, not a real meter benchmark or security guarantee. The full machine-readable run is [`trust_validation_20261028.json`](../reports/research_runs/trust_validation_20261028.json).

## Failure reproduction and diagnosis

Before changing the detector, the reported four-client, three-round, two-local-epoch severe label-skew case was rerun with 400 rows, 10 features, seed 42, sign manipulation at intensity 4, and 25% malicious clients. The attacked client was not flagged (precision 0, recall 0). Its trust remained above the fixed 0.40 cutoff and ended at 0.506, while honest clients ended between 0.685 and 0.704.

The old utility used `0.5 + PR-AUC change`. The sign attacker received utility 0.522 in the first round: PR-AUC measures ranking and may improve after score direction reversal on an imbalanced validation set. Its update norm was 0.551, below the clipping limit of 5, so the integrity signal remained 1.0. Repeating a consistent reversed update also looked temporally consistent. Thus these signals and the fixed trust cutoff failed to distinguish this attacker.

## Implemented detector and protocol

The primary evidence is per-client increase in binary log loss on an internal validation set after applying that client’s update. The final test set is not used for trust or threshold selection. A robust median/MAD threshold is available for online runs. For this controlled study, thresholds are selected from calibration seeds under a maximum 10% calibration honest-client accusation rate; evaluation seeds are disjoint. Each evaluated attack family is excluded from its threshold’s calibration scenarios (leave-one-attack-family-out). Simulated malicious labels are used only to select thresholds on calibration runs. This is supervised simulation calibration, not a deployable guarantee.

Trust decisions record validation harm, threshold, evidence, trust, and aggregation weights. Client IDs and the simulator’s attacker list are not detector inputs. Flagged updates receive reduced weight; configurable recovery restores trust after a temporary anomaly. Evidence variants are utility only, utility plus integrity, utility plus integrity plus temporal evidence, and heterogeneity-adjusted utility. The heterogeneity variant reduces evidence when class-conditional validation loss changes conflict; it remains an unvalidated candidate.

The run has five calibration seeds (42–46) and five disjoint evaluation seeds (52–56), 400 synthetic rows, 10 features, four clients, three rounds, two local epochs, and 25% attackers unless stated otherwise. The 17 conditions cover benign IID/moderate/severe partitions; sign flip 25%/50%; scaling at 2x, 4x, 8x, 4x with 50% attackers, and clipping/no-clipping variants; label flip at 25%/50%; moderate/severe benign client feature shift; and temporary sign attacks with/without recovery. Scenario definitions are in the JSON artifact.

Every aggregation method uses the same partitions and held-out test data within a seed: sample-weighted FedAvg, coordinate trimmed mean, trust-only weighted aggregation, and HATTA (the current equal mixture of trust-only and trimmed mean). Metrics are means over five seeds. Precision, recall, F1, PR-AUC, and honest-client accusation rate are summarized in the artifact with standard deviation and 95% t intervals, clipped to each metric’s valid range. With only five seeds, intervals are wide and estimates are unstable.

## Held out primary results

Detection columns are malicious-client precision / recall / honest-client false accusation rate (FAR). Model columns are electricity-theft fixture F1 / PR-AUC; the fixture is generated classification data and is not electricity data.

| Condition | Detection P / R / FAR | FedAvg F1 / PR-AUC | Trimmed F1 / PR-AUC | Trust-only F1 / PR-AUC | HATTA F1 / PR-AUC |
|---|---:|---:|---:|---:|---:|
| Benign IID | 0.000 / 0.000 / 0.000 | 0.325 / 0.477 | 0.319 / 0.514 | 0.325 / 0.478 | 0.333 / 0.490 |
| Benign moderate | 0.000 / 0.000 / 0.000 | 0.067 / 0.538 | 0.330 / 0.518 | 0.067 / 0.538 | 0.241 / 0.547 |
| Benign severe | 0.000 / 0.000 / 0.050 | 0.190 / 0.578 | 0.375 / 0.497 | 0.190 / 0.576 | 0.335 / 0.531 |
| Sign flip, 25% | 0.900 / 1.000 / 0.067 | 0.139 / 0.349 | 0.175 / 0.424 | 0.204 / 0.545 | 0.216 / 0.506 |
| Sign flip, 50% | 0.900 / 0.900 / 0.100 | 0.146 / 0.122 | 0.140 / 0.181 | 0.155 / 0.307 | 0.137 / 0.191 |
| Scale 2x, 25% | 0.200 / 0.200 / 0.067 | 0.221 / 0.581 | 0.388 / 0.482 | 0.165 / 0.585 | 0.321 / 0.535 |
| Scale 4x, 25% | 0.400 / 0.400 / 0.067 | 0.249 / 0.565 | 0.348 / 0.467 | 0.103 / 0.570 | 0.290 / 0.523 |
| Scale 8x, 25% | 0.400 / 0.400 / 0.067 | 0.257 / 0.561 | 0.343 / 0.474 | 0.103 / 0.572 | 0.302 / 0.533 |
| Scale 4x, 50% | 0.300 / 0.200 / 0.100 | 0.000 / 0.576 | 0.375 / 0.496 | 0.000 / 0.573 | 0.248 / 0.549 |
| Scale 4x, clip 1 | 0.400 / 0.400 / 0.067 | 0.223 / 0.565 | 0.343 / 0.466 | 0.103 / 0.570 | 0.290 / 0.528 |
| Scale 4x, no clip | 0.400 / 0.400 / 0.067 | 0.249 / 0.565 | 0.348 / 0.467 | 0.103 / 0.570 | 0.290 / 0.523 |
| Label flip, 25% | 0.867 / 1.000 / 0.133 | 0.138 / 0.492 | 0.329 / 0.464 | 0.168 / 0.533 | 0.329 / 0.528 |
| Label flip, 50% | 0.900 / 0.900 / 0.100 | 0.174 / 0.129 | 0.197 / 0.285 | 0.187 / 0.325 | 0.207 / 0.336 |
| Benign shift, moderate | 0.000 / 0.000 / 0.050 | 0.237 / 0.511 | 0.410 / 0.512 | 0.237 / 0.512 | 0.368 / 0.531 |
| Benign shift, severe | 0.000 / 0.000 / 0.100 | 0.290 / 0.544 | 0.382 / 0.499 | 0.290 / 0.543 | 0.422 / 0.534 |
| Temporary sign | 0.900 / 1.000 / 0.067 | 0.138 / 0.528 | 0.363 / 0.481 | 0.160 / 0.566 | 0.425 / 0.529 |
| Temporary sign, no recovery | 0.900 / 1.000 / 0.067 | 0.138 / 0.528 | 0.363 / 0.481 | 0.160 / 0.565 | 0.425 / 0.529 |

## Interpretation and known failures

The originally missed sign attack is detected in this repeated controlled setup, but scaling remains difficult: recall is 0.20–0.40 at the 25% attacker fraction and 0.20 at 50%. Label flip recall is 0.90–1.00, with honest FAR up to 0.133. Benign-shift cases have zero recall (no malicious clients) and FAR 0.05 and 0.10. In separate seed-42 smoke runs using the default online median/MAD threshold rather than the cross-family calibrated threshold, both benign and benign-shift data falsely accused one of four clients (FAR 0.25). The calibration result therefore does not validate the default online threshold. These results do not establish fairness under real client distributions.

Integrity evidence did not improve outcomes over utility alone in most cases because update clipping bounded the tested norms. Temporal evidence raised honest accusations in some conditions (up to 0.90 FAR for the 50% sign case in the temporal ablation), making it unsafe as currently defined. Heterogeneity-adjusted utility trades detection for fewer false accusations: it reduced sign-flip recall to 0.80 and label-flip recall to 0.60 in these runs. No evidence variant solves all attack/fairness tradeoffs.

HATTA does not consistently beat trimmed mean in F1 or PR-AUC. Under 25% sign attack it improves F1 (0.216 vs 0.175) and PR-AUC (0.506 vs 0.424), while under 50% sign attack it has slightly lower F1 (0.137 vs 0.140) but slightly higher PR-AUC (0.191 vs 0.181). Under scale 2x, trimmed mean leads F1 while trust-only slightly leads PR-AUC. Conclusions depend on scenario and metric; no superiority claim is supported.

Temporary-attack final trust averaged 0.685 with recovery and 0.657 without recovery (five seeds). Recovery is implemented but this modest difference does not establish a general benefit. `attack_success_rate` is null because these are untargeted sign, scale, and label manipulation scenarios; there is no defined target-class backdoor objective. The paired PR-AUC impact in the artifact is a generic poisoning impact, not attack success.

## Reproduction and remaining research

Run `python scripts/run_trust_validation.py` to regenerate the JSON. The experiment is a single-process logistic-regression simulator; coordinator validation records are available to the simulator and there is no secure aggregation, formal differential privacy, or network privacy boundary. No real theft-label study was run. A separate CEEW real-consumption forecast experiment is documented in [DATASET_CARD.md](DATASET_CARD.md); it does not measure theft detection. The SGCC loader is implemented and fixture-tested, but no SGCC file was supplied.

Next work needs an authorized public theft dataset, customer and chronological split design, substantially more independent seeds, larger client counts and attacker fractions, validation-subgroup analysis, adaptive/colluding/backdoor attacks, and a predeclared target success measure where applicable. Privacy must be evaluated against a stated threat model with accounting before any privacy claim. This is a research prototype, not publication-ready evidence.
