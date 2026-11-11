# Known limitations

- Local single-process simulator only; no multi-organization deployment or isolation.
- Synthetic fixture is not a real meter dataset. SGCC loader/acquisition pipeline is not included.
- The supplied-data runner requires at least five unique meter IDs and at least two meter groups per class for its customer-group holdout; it errors rather than falling back to row splitting when meter IDs are present but insufficient.
- Trust utility uses coordinator-visible validation data. This is not privacy-preserving evaluation.
- HATTA is a provisional heuristic. Heterogeneity is handled by not penalizing update disagreement, not by a validated heterogeneity estimator.
- Backdoor, Gaussian-noise, collusion, model-replacement and stale-update attack simulations are now available alongside label-flip/scale/sign/slow attacks. They are controlled synthetic scenarios, not validated models of field adversaries. The backdoor target prediction rate is a synthetic attack-success proxy. No real-world attack success rate is claimed.
- No formal DP, accountant, secure aggregation, or privacy guarantee.
- No validation-selected threshold, calibration, multiple-seed confidence intervals, or result figure generator yet.
- Saved checkpoints cannot yet resume training.
- Existing API routes have session checks on operational data/artifact operations, but CSRF protection, rate limiting, deployment security, and end-to-end login/browser behavior have not been comprehensively validated.
- `users.json` was sanitized in the working tree, but credentials or tokens committed in earlier Git history require rotation and history cleanup outside this code change.


## Phase-II update (2026-10-30)
See `PHASE_II_MULTI_CLIENT_ARCHITECTURE.md` and `PHASE_II_VALIDATION_2026-10-30.md`. A persistent multi-client registry, client login/dashboard, local client agent, signed update submission, coordinator trust evidence, trust-weighted aggregation and hash-chained audit log have now been added. The limitations in the Phase-II architecture document supersede older statements that there is no client portal or coordinator update workflow. Production blockchain, secure aggregation, end-to-end DP, PostgreSQL and distributed worker deployment remain incomplete.


## Extended implementation update (2026-10-30)
New research/reference components are available: SCAFFOLD control-variate primitives, a conservative full-Gaussian RDP accountant, pairwise-mask secure-sum reference code, a local hash-linked ledger, PSI/calibration utilities, and a SQLite investigation case manager. See `EXTENDED_IMPLEMENTATION_AND_VALIDATION_2026-10-30.md`.

These components do **not** close the production limitations above. In particular, the masked aggregation helper is not a production secure-aggregation protocol; the local hash-linked ledger is not a distributed blockchain; the accountant is not wired end-to-end across all client training; and the case manager is not yet integrated into the dashboard. The client agent continues to exchange logistic-regression parameter vectors rather than federating arbitrary tree/forecasting models. No independently verified Indian theft labels or live DISCOM data integration are included.
\n\n## Attack simulation extension (2026-11-01)\n\nSee [UPGRADE_IMPLEMENTATION_REPORT.md](UPGRADE_IMPLEMENTATION_REPORT.md) for the five additional attack modes, regression tests, and remaining production/research gates.\n