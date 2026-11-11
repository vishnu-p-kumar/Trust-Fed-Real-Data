# TrustFedGrid Phase-II multi-client architecture

## What is now integrated
- Separate client portal at `/client/login` and `/client`.
- Administrator-only client organization creation and suspension at `/dashboard/admin/clients.html`.
- Persistent SQLite client registry, password hashes (PBKDF2-HMAC-SHA256), one-time client-agent secret, dataset metadata, trust history, federated rounds, model-update records, global model and a hash-chained audit event table.
- Independent `client_agent/client_agent.py`: reads a CSV on the client machine, trains a binary logistic model locally from the latest global parameters and transmits only model weights, bias, sample count and round metadata. Raw rows are not posted.
- Coordinator verifies the client-specific secret, update digest, active account, round state, duplicate submissions and model dimensions.
- Coordinator computes integrity, global-model similarity, poisoning heuristic and historical trust evidence, then performs peer-median similarity review at aggregation and trust/sample-count weighted averaging.
- Admin can create a round and aggregate accepted client updates.
- Client dashboard shows organization identity, model version, dataset metadata, update history and trust history.
- Existing administrator, inspector and smart-grid dashboard routes/features are retained.

## First-run setup
1. Copy `.env.example` to `.env`.
2. Set `SMARTGRID_SESSION_SECRET` to a random secret of at least 32 characters.
3. Set `SMARTGRID_ADMIN_EMAIL` and `SMARTGRID_ADMIN_PASSWORD`.
4. For local HTTP development set `SMARTGRID_COOKIE_SECURE=0`. Use HTTPS and secure cookies in deployment.
5. Install `requirements.txt` and start `uvicorn api.main:app --host 0.0.0.0 --port 8000`.
6. Sign in as administrator and open `http://127.0.0.1:8000/dashboard/admin/clients.html`.
7. Create each organization/client. Copy the generated client-agent secret at creation; it is shown once.
8. Create a federated round. Run the agent on each client machine using its own local CSV and the same ordered feature schema.
9. After clients submit, aggregate the round from the admin client-management page.

## Client agent example
See `client_agent/README.md`. The local CSV needs a binary label column (0=normal, 1=theft) and numeric feature columns. Every client must use the same ordered features, units and compatible scaling. The agent refuses an incompatible model dimension.

## Research-paper alignment
The workflow follows the paper's target sequence: local training, update integrity/authentication, reference/peer comparison, adaptive trust evidence, trust-weighted aggregation, audit logging and global-model redistribution. It is a working Phase-II baseline and must be benchmarked against centralized and FedAvg baselines.

## Important limitations; do not represent these as completed
- The audit log is a local SQLite hash chain with verification, not a distributed blockchain network or Hyperledger Fabric deployment.
- The current trust score is a transparent prototype heuristic. It is not a statistically validated or calibrated malicious-client probability; peer similarity can penalize legitimate non-IID clients. Tune thresholds with the paper's planned benign/non-IID/attack experiments.
- The client agent is a binary logistic-regression baseline, not a federated wrapper around every existing theft/anomaly/forecast model. Existing centralized smart-grid features remain available.
- The current coordinator persists submitted parameter vectors in its application database. This is not cryptographic secure aggregation; the coordinator can inspect updates.
- The client secret authenticates the agent and HMAC integrity; use HTTPS. Key rotation, mutual TLS, hardware-backed keys and production identity lifecycle remain future hardening.
- Differential privacy accountant utilities are present from the prior update but are not yet enforced on this client-agent training path. Do not claim end-to-end DP.
- Client dataset registration stores metadata and digest only. It does not upload raw data or prove that a claimed dataset hash matches a dataset the coordinator can inspect.
- SQLite is used for local development. A multi-instance production deployment needs PostgreSQL, shared job queue, migrations, backups and deployment-specific secrets.
- SHAP explanations remain available in the existing centralized prediction pipeline; per-client logistic model SHAP explanations and full client prediction workflows are not integrated here.
- The local CSV agent currently requires both binary classes to train and uses the supplied feature values directly. Establish a shared feature schema and units across clients before running meaningful federation.
- No independently verified Indian electricity-theft-labelled dataset or production utility connection is included.
