# Phase-II validation report — 2026-10-30

## Automated checks
- `python -m pytest -q`: **98 passed**.
- `python -m compileall -q api src client_agent`: passed.
- `node --check` on all dashboard JavaScript files: **12/12 passed**.
- `python run_project.py --num-meters 20 --days 7 --forecast-epochs 1 --skip-report --skip-sample-export`: exited 0; generated 3,360 synthetic readings, trained anomaly/theft/forecasting models and generated the theft heatmap.
- Uvicorn application startup and `/health`: HTTP 200.
- Administrator login: HTTP 200.
- Admin client management page: HTTP 200.
- Admin-created client login and client profile: HTTP 200.
- Live two-client agent test: two separately registered clients each read a local CSV, registered dataset metadata, trained locally, signed and submitted model parameters; both submissions were accepted; coordinator aggregation completed; global model advanced to version 1; normalized aggregation weights summed to 1.0.
- Audit chain verification covered by unit tests.

## Scope preserved
The existing administrator dashboard, inspector dashboard, smart-grid monitoring, theft/anomaly/forecasting pipelines, reports, heatmap, alerts and existing research simulation modules were retained. The new client portal is additive.

## Important limits
This is a working multi-client Phase-II research baseline, not production-ready utility infrastructure:
- The audit ledger is a local SQLite hash chain, not a distributed blockchain network.
- The client-agent federation currently trains a binary logistic-regression baseline on a common numeric feature schema. It does not yet federate every existing central model family.
- The trust score is a heuristic research signal, not calibrated ground-truth client reputation. Peer similarity must be evaluated carefully under non-IID client data.
- The coordinator stores model parameter vectors and can inspect them. Production secure aggregation is not implemented.
- The existing RDP accountant is not yet enforced on the new agent update path; end-to-end differential privacy is not claimed.
- The local agent uses shared feature order/units/scaling as a deployment prerequisite. The smoke test used a tiny synthetic CSV, not real utility data.
- SQLite is used for local development; PostgreSQL, distributed workers, key rotation, mutual TLS, production monitoring, penetration testing and deployment load testing remain.
- The existing central SHAP explanation pipeline remains; per-client explanation of the new logistic federated model is not yet integrated.
- No independently verified Indian theft-labelled dataset or live DISCOM meter integration was supplied.
- Browser visual regression and exhaustive end-to-end testing of every existing dashboard section were not performed.
