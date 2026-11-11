# GridSentinel updated release — 2026-10-29

## Verification performed

- Python compilation: passed.
- JavaScript syntax checks: passed.
- Automated tests: 85 passed.
- Fresh SQLite runtime startup: passed; `/health` returned `ok`.
- Local admin login: passed (HTTP 200).
- Authenticated overview API: passed (HTTP 200).
- ZIP archive integrity: verified after packaging.

The test environment had scikit-learn 1.8.0 while bundled model artifacts were serialized with scikit-learn 1.9.0, causing 15 `InconsistentVersionWarning` warnings in the test suite. Requirements now pin scikit-learn 1.9.0. The 1.8.0 environment run does not prove compatibility under the pinned version; install the requirements and run `python scripts/check_model_compatibility.py` to verify locally.

## Changes in this release

- Fixed clean-start API failure when model prediction frames omit the synthetic `is_theft` label.
- Added API health data-provenance metadata and dashboard warning that model scores are not proof of theft.
- Escaped data-derived text in the theft dashboard table to reduce HTML injection risk.
- Added basic Origin validation for browser state-changing requests, a per-process login attempt limit, and baseline security headers.
- Added leakage-aware, customer-disjoint theft model evaluation and dataset provenance validator.
- Added chronological forecast baseline evaluation and fit the LSTM scaler on the training segment only.
- Added experimental L2 clipping/Gaussian noise and pairwise-mask aggregation simulation helpers.
- Added a durable single-host SQLite job queue utility.
- Added dataset/source, privacy limitations, architecture and remaining production gates documentation.
- Added regression tests for new utilities and security middleware.

## Known remaining gates

- No independently verified Indian theft-label dataset is bundled. CEEW is real Indian meter data but does not contain verified theft labels. The SGCC research benchmark is external, China-origin and its published record lists no license; obtain it only after checking terms. Do not call synthetic or pseudo-labels verified ground truth.
- Differential privacy is a single-release experimental helper and has no multi-round accountant. Pairwise masking is a simulation, not a production cryptographic secure-aggregation protocol.
- The SQLite job queue is a reusable utility but is not yet wired to all long-running API workflows. SQLite remains the current operational database; PostgreSQL migration and multi-worker architecture are not implemented.
- Existing inspection assignment/completion is present; full normalized case-state history, SLA tracking and comprehensive audit workflows remain future work.
- Security middleware is a baseline, single-process control, not a complete security audit. TLS, external rate limiting, secret management, formal CSRF testing, dependency scanning and production deployment review remain necessary.
- E2E smoke tests cover startup, health, login and overview; they do not exhaustively validate every dashboard section, WebSocket reconnect, notification integration, or production load behavior.
