# GridSentinel / TrustFedGrid

## Latest upgrade and verification — 1 November 2026

The live SGCC/CEEW architecture replaces synthetic default training: the theft classifier is trained on SGCC, the consumption forecaster on CEEW, and the default API waits for actual telemetry. The updated regression set contains 154 tests, all of which passed across the documented batch/isolated runs. See [the live architecture and verification report](docs/LIVE_SGCC_CEEW_ARCHITECTURE_2026-11-01.md) for model results, warm-up rules, verification commands and limitations.

The project is a research/demo prototype. Synthetic attack simulations and unit tests do not establish real-world theft-detection accuracy or production security certification.


Trust-Fed-Grid-X is a research prototype for smart-meter analytics. The default runtime uses a theft classifier trained only on the labelled SGCC benchmark and accepts incoming meter telemetry through an authenticated API. A separate next-day consumption forecaster is trained on CEEW Mathura and Bareilly daily aggregates. Synthetic data generation is retained only as an explicitly selected dashboard demonstration and test utility; it is not used to train the default live theft model.

**Research limitations:** SGCC is a historical Chinese utility benchmark and does not establish performance on Indian utility customers. CEEW has no verified theft labels and is used only for consumption forecasting and distribution analysis. The SGCC model requires 30 days of meter history before supervised classification. Alerts are leads for human investigation, not proof of theft or a substitute for independent field verification.

The project includes prototype research utilities for robust aggregation, trust scoring, privacy accounting, masked aggregation and audit ledgers. Their presence does not mean that the application provides end-to-end differential privacy, production secure aggregation, or a distributed blockchain. Read [implementation status](docs/IMPLEMENTATION_STATUS.md), [known limitations](docs/KNOWN_LIMITATIONS.md), and [privacy notes](docs/PRIVACY.md) before interpreting results.

## Contents

- [What the application does](#what-the-application-does)
- [Architecture and data flow](#architecture-and-data-flow)
- [Repository map](#repository-map)
- [Prerequisites](#prerequisites)
- [Install and run locally](#install-and-run-locally)
- [Generate data and models](#generate-data-and-models)
- [Configuration](#configuration)
- [Dashboard and user workflows](#dashboard-and-user-workflows)
- [HTTP API](#http-api)
- [Data and generated artifacts](#data-and-generated-artifacts)
- [Federated learning workflows](#federated-learning-workflows)
- [Optional CEEW and SGCC research](#optional-ceew-and-sgcc-research)
- [Docker](#docker)
- [Tests and evaluation](#tests-and-evaluation)
- [Final functional audit](docs/FINAL_FUNCTIONAL_AUDIT_2026-11-01.md)
- [Limitations and security](#limitations-and-security)
- [Further documentation](#further-documentation)

## What the application does

### Smart-meter analytics

- Trains the default supervised theft classifier from SGCC-labelled customer consumption profiles; it uses 30-day rolling-window features and customer-disjoint train/validation/test splits.
- Accepts physical meter/IoT interval-energy readings through an authenticated telemetry API, stores recent per-meter history, aggregates it to daily kWh and updates live dashboard snapshots.
- Produces SGCC model suspicion probabilities after a meter has 30 calendar days of readings and at least 20 valid daily values. Before that warm-up requirement is met, it reports insufficient history; basic voltage/power-factor checks are separately marked as electrical anomalies, not theft.
- Trains a next-day consumption forecaster on CEEW Mathura and Bareilly daily aggregates. The learned model is selected only when its validation MAE beats a persistence baseline.
- Keeps synthetic Bengaluru data generation as an explicit demo mode (`--demo-synthetic`); it is not part of the default theft-model training path.

### Operator and client workflows

- Admin login and summary views, client organization management, bounded research experiment controls, and federated update/audit views.
- Inspector accounts, area-scoped suspicious-meter views, task assignment and task completion.
- Separate client login and dashboard for organization identity, dataset metadata, federated rounds, submitted updates and trust history.
- A local CSV client agent that trains a binary logistic-regression model and sends model parameters and metadata to the coordinator. It does not upload raw meter rows.

These workflows are implemented in a primarily single-process application. They are useful for integration and research demonstrations, not a ready-made multi-utility production service.

## Architecture and data flow

```text
SGCC labelled benchmark ── 30-day windows ── SGCC live theft classifier
                                                     │
Physical meters / IoT gateway ── POST /api/telemetry/readings
                                                     │
                              per-meter daily history + 30-day warm-up
                                                     │
                              live theft suspicion score + alerts
                                                     │
CEEW Mathura/Bareilly ── CEEW next-day forecaster ────┤
                                                     │
                                  FastAPI + SQLite + /ws/live
                                                     │
                                       browser dashboard

Optional synthetic data ── demo mode and automated test fixtures only

Federated client CSV → local logistic training → signed parameter update
                                               → prototype coordinator
```

The live telemetry classifier and the admin research-experiment endpoint both use SGCC-derived data by default. The `/api/research/experiments` route loads `datasets/sgcc/processed/sgcc_meter_features.csv.gz` and passes the labelled customer table into the federated experiment, which performs customer-group holdouts. Generated `make_classification` data is retained only for explicit offline smoke tests and controlled synthetic robustness fixtures. The federated client/coordinator portal remains a separate prototype workflow; all coordinator code and registered clients can still run within one application/database, so this is not network-isolated federation. The central coordinator can inspect submitted parameter updates.

## Repository map

| Path | Purpose |
|---|---|
| `api/main.py` | FastAPI app, authentication, runtime loop, REST/WebSocket routes, dashboard serving and orchestration. |
| `src/` | Data generation and preprocessing, feature engineering, models, forecasting, scoring, alerts, reporting, drift, pole monitoring, investigations, security and federated research code. |
| `src/federated/` | Synthetic experiments, partitions, aggregators, attacks, trust logic, client registry/coordinator, checkpoint and ledger helpers. |
| `src/security/` | Privacy utilities, privacy accountant, reference secure-sum helper, TOTP and rate-limit adapter. These are not a complete production privacy/security stack. |
| `dashboard/` | Static front end: main operator dashboard, admin pages, inspector and client portals, reports and shared components. No Node build step is required. |
| `client_agent/` | Standalone client-side CSV training agent and its usage guide. |
| `utils/helpers.py` | Project paths, generation defaults, serialization and SQLite helpers. |
| `scripts/` | Dataset preparation, evaluation, experiment and validation command-line tools. |
| `tests/` | Pytest coverage for API, data, analytics, workflows and research components. |
| `data/raw/` | Place externally acquired raw data here; do not commit private/customer data. |
| `data/processed/` | Generated training/live datasets and normalized research inputs. |
| `data/labels/` | Provenance guidance and examples for externally sourced labeled data; no verified theft dataset is bundled. |
| `dataset/` | Output location for the optional synthetic demonstration dataset; not a default training source. |
| `models/` | SGCC live theft and CEEW forecast artifacts; older classifier/forecast artifacts are tagged as optional synthetic-demo caches only. |
| `database/` | SQLite runtime databases and local workflow state. |
| `reports/` and `maps/` | Generated PDF/JSON reports, experiment output and heatmaps. |
| `sample_outputs/` | Example API request/response payloads. |
| `docs/` | Architecture, methods, data cards, experiments, validation records, limitations and research notes. |
| `run_project.py` | SGCC/CEEW model-training bootstrap command; optionally starts the API. |
| `run.md` | Extended Windows PowerShell run guide. |
| `docker-compose.yml` | Local API/dashboard containers plus optional production-profile infrastructure services. |

## Prerequisites

- Python 3.11 is the version used by the Docker image and is a good local choice.
- Windows PowerShell commands below assume the repository root (the directory containing `run_project.py`). Other operating systems can use equivalent virtual-environment and environment-variable commands.
- A frontend toolchain is not required; the dashboard is static HTML, CSS and JavaScript.
- The default training sources (SGCC and CEEW) are bundled. The default runtime waits for meter telemetry; synthetic data is generated only when the optional demo mode is explicitly selected. Internet access and an OpenWeather key are optional; optional integrations and some model libraries may require additional packages or credentials.

## Install and run locally

### 1. Create an environment and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell does not allow activation, call the environment interpreter directly, for example `.\.venv\Scripts\python.exe -m pip install -r requirements.txt`, and use that interpreter for the remaining commands. Install test-only packages with `python -m pip install -r requirements-test.txt`. Install `requirements-advanced.txt` only for optional advanced workflows such as model optimization.

The requirements include substantial numerical, ML and visualization packages; installation and first model training can take time. Some forecasting/model features have fallback paths if optional model dependencies or artifacts are not available.

### 2. Configure local login and cookies

The API loads `.env` from the repository root when it starts; variables already present in the process environment take precedence. Start from `.env.example`, then replace the example admin password and session secret with your own values. Keep `.env`, credentials, client-agent secrets and private data out of version control.

For local HTTP development, set a session secret of at least 32 characters, an admin email/password, and disable secure-only cookies. For example, in PowerShell:

```powershell
$env:SMARTGRID_ADMIN_EMAIL = "admin@example.test"
$env:SMARTGRID_ADMIN_PASSWORD = "choose-a-local-password"
$env:SMARTGRID_SESSION_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:SMARTGRID_COOKIE_SECURE = "0"
$env:SMARTGRID_CORS_ORIGINS = "http://127.0.0.1:8000,http://localhost:8000"
```

Use the same PowerShell window to start the API so the variables are inherited. `SMARTGRID_COOKIE_SECURE=0` is only for local HTTP development; use HTTPS and secure cookies for a deployed service. Inspector accounts and federated client accounts are created through their respective admin workflows.

### 3. Train the default models (no synthetic training)

The standard command trains the live theft classifier from SGCC and the consumption forecaster from CEEW:

```powershell
python run_project.py
```

The SGCC training job uses one deterministic, randomly located 30-day window per customer to keep memory bounded. It reports customer-disjoint test metrics and saves `models/sgcc_live_theft_model.pkl` plus `models/sgcc_live_theft_metadata.json`. CEEW forecasting saves `models/ceew_consumption_forecaster.pkl` and its metadata. At API startup, missing model artifacts are built from the bundled SGCC/CEEW sources when possible.

To explicitly run the old synthetic dashboard demonstration (not the default and not suitable for claiming research performance):

```powershell
python run_project.py --demo-synthetic --num-meters 20 --days 7 --forecast-epochs 1
```

Common options:

| Option | Effect |
|---|---|
| `--skip-training` | Use existing SGCC/CEEW model artifacts; errors if the SGCC live model is missing. |
| `--sgcc-target-recall 0.40` | Validation recall target used to select the live classifier threshold. |
| `--sgcc-windows-per-customer 1` | Number of 30-day SGCC windows per customer; 1 is the memory-efficient default. |
| `--demo-synthetic` | Explicitly enable synthetic-data generation and the legacy synthetic app path. |
| `--num-meters N`, `--days N`, `--full-scale` | Configure the synthetic demo only. |
| `--forecast-epochs N`, `--optimize-models` | Configure synthetic demo training only. |
| `--start-api` | Start FastAPI after model preparation (port 8000). |

The default runtime does not create or replay synthetic meter data. It waits for incoming telemetry. Set `SMARTGRID_DEMO_MODE=1` only when you deliberately want the synthetic replay demonstration.

### 4. Start the API

Start it directly after generating artifacts:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Or bootstrap and start together with `python run_project.py --start-api`. Keep the terminal open while using the application; stop with `Ctrl+C`.

Open `http://127.0.0.1:8000/login` to sign in. The API serves the dashboard and portal assets on the same origin. Common local URLs:

- Login: `http://127.0.0.1:8000/login`
- Operator dashboard: `http://127.0.0.1:8000/dashboard/`
- Admin client management: `http://127.0.0.1:8000/dashboard/admin/clients.html`
- Inspector portal: `http://127.0.0.1:8000/inspector`
- Client portal: `http://127.0.0.1:8000/client`
- Health: `http://127.0.0.1:8000/health`
- Interactive OpenAPI docs: `http://127.0.0.1:8000/docs`

Check health from another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
```

A degraded response indicates missing or unavailable runtime artifacts; inspect the payload and regenerate with `python run_project.py` when appropriate.

## Configuration

The main settings read by the application include:

| Variable | Default / behavior |
|---|---|
| `SMARTGRID_ADMIN_EMAIL` | Admin identity; configure for local use. |
| `SMARTGRID_ADMIN_PASSWORD` | Admin password; replace the example value. |
| `SMARTGRID_SESSION_SECRET` | Session-signing secret; at least 32 characters. |
| `SMARTGRID_COOKIE_SECURE` | Secure cookie flag; keep enabled behind HTTPS, set `0` only for local HTTP. |
| `SMARTGRID_CORS_ORIGINS` | Comma-separated exact allowed browser origins; configure to match the app origin(s). |
| `SMARTGRID_UPDATE_INTERVAL` | WebSocket snapshot refresh interval in seconds; default 4. In live mode, meter snapshots are driven by incoming telemetry. |
| `SMARTGRID_DEMO_MODE` | Enables synthetic replay mode when set to `1`; default `0` (live telemetry mode). |
| `SMARTGRID_SGCC_TARGET_RECALL` | Validation recall target for the SGCC classifier threshold; default `0.40`. |
| `SMARTGRID_SGCC_WINDOWS_PER_CUSTOMER` | Number of training windows per SGCC customer; default `1` for memory efficiency. |
| `SMARTGRID_ENABLE_ALERTS` | Enables configured alert delivery when set to `1`; default `0`. Configure provider credentials before enabling. |
| `OPENWEATHER_API_KEY` | Optional weather integration key; simulated weather is used when unavailable. |
| `TRUSTFED_DB_PATH` | Federated client/coordinator SQLite database path (see `.env.example`). |
| `TRUSTFED_CASE_DB_PATH` | Optional investigation case database path. |

Email and Telegram settings are also listed in `.env.example`. Keep integrations disabled until their credentials and destinations are deliberately configured. Runtime SQLite tables, generated data and models are local files and need suitable persistence/backup arrangements if retained.

## Dashboard and user workflows

The main dashboard under `dashboard/` contains views for overview, live monitoring, theft detection, anomaly detection, demand forecasts, energy efficiency, pole monitoring, heatmaps, weather impact, alerts and reports. It reads API endpoints and the `/ws/live` stream. The dashboard snapshot interval defaults to four seconds; in live mode, new readings are pushed when telemetry is ingested.

Other workflows:

- **Admin:** manage federated client organizations, start and aggregate rounds, inspect trust/audit information, review investigation records, and manage inspector accounts.
- **Inspector:** view area-filtered cases, inspect meter details, and record assigned inspection task completion.
- **Federated client:** review its organization profile, register dataset metadata, see rounds/update/trust history, and submit local model updates through the client agent.

The static dashboard can be previewed separately with `python -m http.server 8080 --directory dashboard`, but authentication and same-origin routes are intended to be used through the FastAPI-served application. For a separate origin, configure `SMARTGRID_CORS_ORIGINS` and the frontend API base deliberately.

## HTTP API

The interactive API schema at `/docs` is the authoritative request/response reference. The main route groups are:

| Routes | Purpose |
|---|---|
| `GET /health` | Runtime and artifact health. |
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/session` | Admin/inspector session workflow. |
| `GET /overview`, `/meters`, `/anomalies`, `/theft`, `/weather-impact`, `/forecast`, `/risk-scores`, `/efficiency`, `/drift-report` | Operational analytics. |
| `GET /api/pole-status`, `/api/pole-tamper-alerts`, `/api/pole-energy-balance` | Pole monitoring results. |
| `POST /predict` | Score one meter reading or a list of readings using the centralized inference pipeline. |
| `GET /artifacts/daily-report`, `/artifacts/drift-report`, `/artifacts/sample-overview`, `/artifacts/heatmap` | Download generated outputs. |
| `GET /ws/live` | Authenticated live snapshot WebSocket. |
| `/api/inspectors`, `/api/inspector/*` | Inspector management and task workflow; authorization is role-scoped. |
| `/api/clients`, `/api/client/*`, `/api/federated/*`, `/api/admin/trust`, `/api/admin/audit` | Federated client portal/coordinator workflow; authorization is role-scoped. |
| `/api/admin/investigations/*`, `/api/admin/analytics/summary` | Admin investigation and summary operations. |
| `/api/research/experiments` | Bounded admin research experiment submission and result retrieval. |

Operational data and artifact routes require an authenticated session. Use `/docs` for schemas, limits and exact response fields. Prediction inputs are validated and reject unexpected fields; the numeric constraints are defined by the `MeterReading` model in `api/main.py`.

## Data and generated artifacts

### Default live theft detection: SGCC

The default theft classifier is trained from `datasets/sgcc/raw/sgcc_data.csv` using `src/sgcc_live_model.py` and `scripts/train_sgcc_live_model.py`. It uses one 30-calendar-day consumption window per SGCC customer, with 26 label-independent features. The window start is sampled deterministically across the historical period. The customer ID is used only to keep all rows from a customer in one split; it is never a model feature. The training/evaluation split is customer-disjoint.

Artifacts:

- `models/sgcc_live_theft_model.pkl`: SGCC-trained live classifier.
- `models/sgcc_live_theft_metadata.json`: feature schema, selected threshold, data provenance and held-out metrics.
- `datasets/sgcc/processed/sgcc_meter_features.csv.gz`: longer-profile research benchmark features; this is a separate research pipeline.

**Live input contract:** `consumption_kwh` sent to the telemetry endpoint must be interval energy, not a cumulative meter register. The API aggregates interval energy into daily totals. A meter must have 30 calendar days of retained history and at least 20 valid daily values before the SGCC classifier returns a theft probability. Before then the system reports `Insufficient History`; an out-of-range voltage or low power-factor check may produce `Anomaly`, but that is not a theft classification.

### CEEW consumption forecasting

The CEEW Mathura and Bareilly daily aggregate files under `datasets/ceew/raw/` train a separate next-day consumption forecaster. The training job uses per-meter chronological splits, compares a HistGradientBoosting regressor against a persistence baseline, and selects the learned model only when its validation MAE is lower. It never uses or creates theft labels.

Artifacts:

- `models/ceew_consumption_forecaster.pkl`
- `models/ceew_consumption_forecaster_metadata.json`

A live meter needs at least seven valid daily readings before a next-day forecast can be emitted. Forecast residuals are anomaly proxies, not verified theft indicators.

### Optional synthetic demonstration data

`src/data_generator.py` can still create simulated Bengaluru histories and theft scenarios, but only when explicitly run with `python run_project.py --demo-synthetic`. Such data is useful for UI demonstrations and software tests. It is not used by the default SGCC theft model or the CEEW forecasting model. The generated artifacts include `dataset/smart_meter_data.csv`, `data/processed/smart_meter_sample.csv`, and `data/processed/live_simulation.csv`.

### Sending live telemetry

After signing in to the API, send interval readings to `POST /api/telemetry/readings` (up to 500 readings per request). The request body is a JSON array. Example:

```json
[
  {
    "meter_id": "METER-001",
    "timestamp": "2026-11-01T10:15:00",
    "consumption_kwh": 0.18,
    "voltage": 229.5,
    "current": 3.2,
    "power": 0.74,
    "power_factor": 0.91,
    "area": "Whitefield",
    "region": "Bengaluru",
    "latitude": 12.9698,
    "longitude": 77.7499
  }
]
```

The API persists records in `database/meter_data.db` (`live_telemetry_readings`), updates the per-meter history, scores ready meters, and broadcasts the updated dashboard snapshot through `/ws/live`. API access requires an authenticated session. The older `/predict` route also feeds readings into the live per-meter history in default live mode.

### Synthetic 800-meter live feed

For this local checkout, `SMARTGRID_SYNTHETIC_LIVE_METERS=1` in `.env` starts the clearly labeled sender whenever you start the API with `run_project.py --start-api`. It sends 800 meters every five minutes. The fleet maps ten meters to each of 80 poles across Whitefield, Koramangala, and Electronic City. Its fixed demo scenarios provide one theft marker above 0.85, five electrical anomalies, and four pole-tamper markers. Each finding stays active across readings and app restarts until an inspector completes a task for the affected meter. Starting a new demo run re-arms previously completed synthetic scenarios.

The sender command can also be run manually when `run_project.py` is not managing it:

```powershell
.\.venv\Scripts\python.exe scripts\synthetic_live_meter_sender.py
```

It authenticates with the ignored local `.env`, sends 30 days of synthetic daily warm-up when needed, then streams readings for 800 simulated meters every five minutes by default. The dashboard and `/health` identify these readings as synthetic. Synthetic history is stored as one daily aggregate per meter to keep the database bounded. Stop the manually run sender with `Ctrl+C`; when `run_project.py` manages the sender, stopping the API also stops it.

Use `--once` to seed and send one snapshot, `--count 800` to set the fleet size, `--interval-seconds 300` to change the cadence, or `--backfill-days 0` to skip the synthetic history warm-up. These values are only for UI and integration demos; simulated alerts and theft probabilities are not evidence about real meters. In live mode, next-day forecasts use the CEEW consumption model; next-hour and next-week card values are derived averages and extrapolations, not separate LSTM/Transformer forecasts.

## Federated learning workflows

### In-process research simulation

`src/federated/experiment.py` supports client partitioning, local training, FedAvg and robust/trust-oriented aggregation comparisons, and controlled simulated attacks. The admin API route `/api/research/experiments` supplies the prepared, labelled SGCC feature table automatically and records dataset provenance in its response. Passing no dataframe directly to `run_experiment()` intentionally uses a generated classification fixture; keep that path for offline smoke tests and synthetic sensitivity experiments only. For example:

```powershell
python -c "from src.federated.experiment import run_experiment; result = run_experiment({'samples': 400, 'features': 10, 'clients': 4, 'rounds': 3, 'local_epochs': 2, 'partition': 'severe', 'attack': 'sign', 'seed': 42}, output_dir='reports/research_runs/smoke'); print(result['metrics'])"
python scripts/run_trust_validation.py
```

The generated fixture is not electricity data. The default admin API research route does not use that fixture: it loads the prepared SGCC customer-level feature table and performs meter-group holdouts. The API response includes `dataset_provenance` (`dataset`, row count, meter count, feature count, label counts and `synthetic_training: false`). Trust scores and HATTA are experimental heuristics; their behavior varies by attack and data distribution. The trust study report documents false accusation and missed attack cases. Do not use the score as sole evidence for punitive actions.

### Multi-client coordinator prototype

The Phase-II workflow is described in [the multi-client architecture note](docs/PHASE_II_MULTI_CLIENT_ARCHITECTURE.md). An administrator creates client organizations and a round. Each organization runs `client_agent/client_agent.py` against its local CSV and submits a signed parameter update; the coordinator then validates and aggregates accepted updates. The client agent supports a binary logistic regression baseline with shared, ordered numeric features. The coordinator stores and can inspect submitted parameter vectors; no raw CSV rows are sent by the agent.

Follow [the client agent guide](client_agent/README.md) for the exact command and feature requirements. Use HTTPS outside localhost, agree on feature names/order/units and label semantics across clients, and treat secrets as credentials. Dataset registration records metadata; it does not independently verify the dataset's contents.

This prototype is not network-isolated federation, cryptographic secure aggregation, or complete end-to-end differential privacy. The application-level federated agent path does not enforce a formal privacy budget. See the limitations documents before handling real utility data.

### Research components

Additional modules include FedProx and Multi-Krum experiment primitives, SCAFFOLD control-variate helpers, Gaussian privacy accounting utilities, pairwise-mask secure-sum reference code, checkpoint helpers and a local hash-linked ledger. Integration and guarantees vary by component. In particular, the reference secure-sum helper is not production cryptography, the local ledger is not a distributed blockchain, and the accountant does not establish application-wide DP. See [implementation updates](docs/IMPLEMENTATION_UPDATES_2026-10-30.md) and [extended validation](docs/EXTENDED_IMPLEMENTATION_AND_VALIDATION_2026-10-30.md).

## Optional CEEW and SGCC research

### CEEW consumption data

The supplied CEEW Mathura/Bareilly files support consumption profiling, forecasting and unlabeled analysis. They do not contain verified theft labels. To profile source CSVs without normalizing them:

```powershell
python scripts/prepare_ceew_dataset.py --profile-only --chunksize 200000 --output reports/research_runs/ceew_profile --input "C:\path\to\source.csv" "C:\path\to\another.csv"
```

To normalize the daily aggregates and run the documented forecast experiment, use the commands and file names in [dataset sources](docs/DATASETS.md) and [dataset card](docs/DATASET_CARD.md). High-frequency sources may be too large for the current in-memory forecast runner. The recorded CEEW results are consumption forecasting results, not theft detection; the trained approaches did not outperform the persistence baseline in the documented evaluation.

### SGCC theft dataset

The user-provided SGCC benchmark and its engineered customer-level feature table are included in this research package. The loader and benchmark scripts preserve customer-disjoint evaluation. SGCC is historical Chinese utility data; it is not Indian utility validation. The uploaded archive does not include individual inspection records or an explicit redistribution licence. Verify the applicable upstream terms before redistributing the raw data. See [the dataset card](datasets/sgcc/README.md) and [uploaded-data evaluation](docs/UPLOADED_DATASET_EVALUATION_2026-11-01.md).

## Docker

The default Compose services run the API on port 8000 and a separate Nginx static dashboard on port 8080. The API also serves its own dashboard and authentication routes. Persistent local directories are mounted for data, database, dataset, maps, models, reports and sample outputs.

Create a local `.env` file from the example and replace the placeholder credentials before starting Compose:

```powershell
Copy-Item .env.example .env
# Edit .env: set a unique SMARTGRID_ADMIN_PASSWORD and a random
# SMARTGRID_SESSION_SECRET of at least 32 characters. Keep
# SMARTGRID_COOKIE_SECURE=0 for local HTTP; use 1 behind HTTPS.
docker compose up --build
```

The API container receives the admin credentials, session secret, cookie mode and CORS allow-list from `.env`; the CORS list must include the browser origin on port 8080 as well as the API origin on port 8000. The default Compose invocation starts the `api` and `dashboard` services. PostgreSQL, Redis and the PostgreSQL worker are under the `production` profile (`docker compose --profile production up --build`); set `POSTGRES_PASSWORD` in `.env` before enabling that profile. Their presence is infrastructure scaffolding; the main application persistence and workflows are not fully migrated to PostgreSQL/Redis or a distributed worker architecture. Docker Compose itself was not executable in the audit environment, so validate the deployment profile on a machine with Docker installed. Configure and review secrets before use. The container exposes the API on all interfaces; restrict network access appropriately.

## Tests and evaluation

Install test dependencies if needed, then run from the repository root:

```powershell
python -m pytest -q
```

Useful focused evaluation scripts include:

```powershell
python scripts/check_model_compatibility.py
python scripts/evaluate_theft_models.py --help
python scripts/evaluate_forecasting.py --help
python scripts/run_robustness_suite.py --help
python scripts/run_privacy_utility.py --help
python scripts/run_sgcc_adversarial_suite.py --help
```

Consult each script's help for required inputs and output paths. The live SGCC/CEEW upgrade is covered by the full regression suite; see `docs/LIVE_SGCC_CEEW_ARCHITECTURE_2026-11-01.md` for the current run results and the final package test count. See [the final functional audit](docs/FINAL_FUNCTIONAL_AUDIT_2026-11-01.md) for the actual runtime and workflow checks. Test success covers implemented code paths; it does not prove theft label validity, real-world model performance, production security, cryptographic security or privacy guarantees.

## Limitations and security

- Synthetic electricity readings and labels are available only through the explicitly selected demo mode and test fixtures; they are not used to train the default live theft model.
- CEEW data is unlabeled for theft. No independently verified Indian theft-labeled dataset is bundled.
- The live service, coordinator, and local databases are primarily single-process/local-development components.
- Federated client updates are visible to the coordinator; secure aggregation and end-to-end differential privacy are not implemented on the client workflow.
- Trust and poisoning scores are heuristic research signals and may penalize legitimate non-IID client behavior.
- The local hash-linked audit log is not a distributed blockchain network. Fabric chaincode under `blockchain/fabric-chaincode/` is a separate artifact and is not evidence of an integrated Fabric deployment.
- Browser controls and session checks do not replace security review, deployment hardening, TLS, CSRF defenses, centralized rate limiting, secret lifecycle management, backups or production monitoring.
- Do not use model outputs alone to accuse a customer or take enforcement action. Require evidence and human review.
- Do not commit `.env`, credentials, customer readings, dataset archives, client secrets or other private information.

## Further documentation

- [Architecture](docs/ARCHITECTURE.md) · [Method](docs/METHOD.md) · [Experiments](docs/EXPERIMENTS.md)
- [Implementation status](docs/IMPLEMENTATION_STATUS.md) · [Known limitations](docs/KNOWN_LIMITATIONS.md) · [Privacy](docs/PRIVACY.md) · [Threat model](docs/THREAT_MODEL.md)
- [Dataset sources](docs/DATASETS.md) · [Dataset card](docs/DATASET_CARD.md) · [Reproducibility](docs/REPRODUCIBILITY.md)
- [Phase-II client architecture](docs/PHASE_II_MULTI_CLIENT_ARCHITECTURE.md) · [Trust validation results](docs/TRUST_VALIDATION.md)
- [Windows setup details](run.md) · [Client agent instructions](client_agent/README.md)
#

## Extended research validation workflows (2026-11-01)

The experiment engine now compares `fedavg`, `fedprox`, `fedavg_dp`, `trimmed_mean`, `multi_krum`, `trust`, and `hatta`. Run a multi-seed baseline and trust-evidence ablation study with:

```bash
python scripts/run_fl_comparison.py --seeds 11,23,37,53,71 --clients 8 --rounds 5 --samples 1200
```

For attack scenarios, append `--include-attacks`. For a raw CEEW-to-forecast workflow:

```bash
python scripts/run_ceew_pipeline.py --input /path/to/CEEW.csv --interval 3min
```

CEEW consumption measurements are unlabeled for theft; they support forecasting and anomaly-proxy analysis, not supervised theft classification. A real-world theft evaluation requires inspection-confirmed labels and a provenance manifest. Start from `data/labels/verified_theft_provenance.template.json`, fill it with the utility's actual audit metadata, and run:

```bash
python scripts/evaluate_verified_theft.py --input /path/to/inspection_labelled.csv --provenance /path/to/provenance.json
```

The manifest is owner-attested and must be independently audited. See `docs/COMPLETION_AND_VALIDATION_2026-11-01.md` for implementation scope and explicit production limitations. In particular, the pairwise-mask secure aggregation module is a research reference, not an audited production cryptographic protocol.


## Extended research validation (2026-11-01)

Additional research scripts are available:

- `scripts/run_sensitivity_analysis.py` — malicious-client ratio, trust threshold, trim fraction, local epochs, client participation, HATTA blend weight and benign-shift sweeps.
- `scripts/run_privacy_utility.py` — Gaussian DP-FedAvg privacy/utility curve with full-participation RDP accounting.
- `scripts/evaluate_generalization.py` — leave-one-location-out, seasonal and chronological evaluation for labelled meter data.
- `scripts/run_fl_comparison.py` — centralized/local-only, FedAvg, DP-FedAvg, FedProx, Trimmed Mean, Multi-Krum, trust-weighted and HATTA comparisons.

See `docs/RESEARCH_VALIDATION_2026-11-01_FINAL.md` for the exact commands, measured synthetic benchmark results, limitations and remaining external validation gates. The included smoke fixtures are not real theft labels.


## Uploaded real-data integration (SGCC + CEEW)

This section and `docs/UPLOADED_DATASET_EVALUATION_2026-11-01.md` supersede the pre-upload data availability notes in earlier validation reports.

This release includes a reproducible SGCC-labelled theft benchmark and CEEW consumption-only ingestion workflow.

### SGCC labelled benchmark

The raw SGCC wide-format CSV is stored at `datasets/sgcc/raw/sgcc_data.csv`; its dataset card is `datasets/sgcc/README.md`.

```bash
python scripts/prepare_sgcc_dataset.py --input datasets/sgcc/raw/sgcc_data.csv
python scripts/run_sgcc_benchmark.py --input datasets/sgcc/processed/sgcc_meter_features.csv.gz --seeds 11,23,37,53,71
python scripts/run_sgcc_federated_multiseed.py --csv datasets/sgcc/raw/sgcc_data.csv --seeds 11,23,37 --clients 4 --rounds 2 --local-epochs 1 --partition severe
```

The SGCC benchmark is historical daily data from a Chinese utility, not a live feed or Indian utility evaluation. The published `FLAG` label is used as supplied. The archive does not include individual inspection records or an explicit redistribution licence; check upstream terms before redistribution. See `docs/UPLOADED_DATASET_EVALUATION_2026-11-01.md`.

### CEEW Mathura/Bareilly consumption data

The uploaded CEEW archive was truncated before its central directory. The recovery tool validates complete ZIP members using ZIP64 sizes and CRC32, recovers complete CSV members from the damaged archive, and reports any incomplete member:

```bash
python scripts/recover_ceew_zip.py --archive /path/to/archive.zip --output-dir datasets/ceew/recovered
python scripts/ingest_ceew_sources.py --input datasets/ceew/recovered/*.csv --output-dir datasets/ceew/processed
```

Seven members were recovered from the damaged archive; `SM Cleaned Data MH2021.csv` was later re-uploaded separately and validated as a complete 550,560-row source. The combined CEEW audit now covers eight files and 21,439,039 readings. CEEW has no verified theft label, so use it for forecasting, consumption analysis, client heterogeneity and anomaly proxies only—not supervised theft classification. See `datasets/ceew/README.md`.

### Measured results

See:
- `reports/research_runs/sgcc_customer_disjoint_benchmark.json`
- `reports/research_runs/sgcc_federated_multiseed.json`
- `reports/research_runs/ceew_upload_ingestion.json` (generated from the recovered complete CEEW members)
- `docs/UPLOADED_DATASET_EVALUATION_2026-11-01.md`

All metrics are measured as reported; no target accuracy is forced. Accuracy must be interpreted alongside recall, F1, PR-AUC, false-positive rate and MCC because theft labels are imbalanced.


### Final functional verification
The final package audit supersedes earlier test counts in historical release notes. The earlier synthetic-default release audit passed 147 tests. The current live SGCC/CEEW architecture has its own updated regression and workflow record in `docs/LIVE_SGCC_CEEW_ARCHITECTURE_2026-11-01.md`; use that report for the current behavior.


## Adaptive trust-aware publication experiments (2026-11-01)

This update corrects the trust recovery path so it uses the measured validation contribution utility instead of treating every non-flagged update as perfectly useful. The trust evidence combines training-only validation harm, pre-clipping update integrity and temporal update consistency. HATTA combines trust-weighted aggregation with coordinate trimmed mean. The validation set is coordinator-visible in this simulation; this is not a privacy-preserving contribution protocol.

Reproduce the three publication-oriented experiment groups:

```bash
python scripts/run_robustness_suite.py --seeds 11,23,37 --clients 6 --rounds 4 --samples 900 --output reports/research_runs/publication_robustness_2026-11-01.json
python scripts/run_privacy_utility.py --seeds 11,23,37 --clients 6 --rounds 5 --samples 900 --output reports/research_runs/publication_privacy_utility_2026-11-01.json
python scripts/run_sgcc_adversarial_suite.py --seeds 11,23,37 --clients 6 --rounds 2 --max-customers 5000 --output reports/research_runs/sgcc_adversarial_suite_2026-11-01.json
```

The first two robustness runs use controlled synthetic fixtures; the SGCC adversarial pilot uses a deterministic stratified 5,000-customer subset of the labelled historical benchmark and simulated client attacks. The pilot is not a full-cohort evaluation. Its client-detection false-accusation rate remains material, so do not claim reliable attacker identification from these results. The privacy curve covers only the configured Gaussian-noisy client-update mean under replacement adjacency and conservative full-participation RDP composition; it does not cover HATTA validation-derived trust evidence or the whole application. See `docs/ADAPTIVE_TRUST_AWARE_RESEARCH_METHOD.md` and `docs/PUBLICATION_EXPERIMENTS_2026-11-01.md` for methods, measured results and limitations.


## Research upgrade (2026-11-01)

This release adds temporal profile features, validation-only model/threshold selection,
adaptive low-and-slow and mimic attack simulations, multi-round trust suspicion,
optional DP-noised trust evidence, Page-Hinkley drift monitoring, permutation
importance, and CPU edge-efficiency proxy benchmarking.

See `docs/RESEARCH_UPGRADE_VALIDATION_2026-11-01.md` for measured results,
limitations and reproduction commands, and `docs/RESEARCH_CONTRIBUTIONS.md`
for the four contribution map. Do not describe the research trust-evidence
mechanism as end-to-end differentially private or the workstation edge proxy
as physical meter deployment.

Run the principal research checks:

```bash
python scripts/evaluate_theft_models_tuned.py --seeds 11,23,37,53,71
python scripts/run_sgcc_adversarial_suite.py --seeds 11,23,37
python scripts/run_robustness_suite.py --seeds 11,23,37
python scripts/run_privacy_utility.py --seeds 11,23,37,53,71
python scripts/benchmark_edge_efficiency.py
python scripts/explain_sgcc_model.py
pytest -q
```

## PR-AUC and cross-utility validation upgrade (2026-11-01)

The latest extension adds:
- Full 42,372-customer SGCC model selection using validation PR-AUC (balanced ExtraTrees vs. HistGradientBoosting).
- Validation-only threshold selection with a recall floor of 0.40; the threshold does not change PR-AUC.
- CEEW Mathura and Bareilly feature-shift comparison against SGCC (Wasserstein distance and PSI). CEEW is unlabelled, so no theft PR-AUC is reported.
- Optional TDD2022 download/evaluation adapter. TDD2022 is based on OEDI measured consumption but its theft labels are synthetically generated; keep its results separate from SGCC.

Reproduce the current measured extension:

```bash
python scripts/optimize_sgcc_pr_auc.py --seeds 11,23,37 --target-recall 0.40
python scripts/evaluate_ceew_domain_shift.py
pytest -q
```

Optional external TDD2022 experiment:

```bash
python scripts/download_tdd2022.py
python scripts/evaluate_tdd2022_external.py --seeds 11,23,37 --target-recall 0.40
```

See `docs/PR_AUC_AND_CROSS_UTILITY_UPGRADE_2026-11-01.md`. A second utility's independently verified theft labels remain necessary for a true cross-utility supervised PR-AUC claim.

### Start the application

After installing the dependencies, run the API and dashboard backend with:

```bash
python run_project.py --start-api
```

The API health check is available at `http://127.0.0.1:8000/health`. The default live mode waits for incoming meter telemetry; it does not replay a synthetic feed. See the Live telemetry section above for the authenticated ingestion endpoint and warm-up requirements.

### Default live model artifact versus legacy demo artifacts

`models/sgcc_live_theft_model.pkl` and `models/sgcc_live_theft_metadata.json` are the default live theft-detection artifacts, trained from SGCC only. `models/ceew_consumption_forecaster.pkl` and its metadata are the default CEEW forecasting artifacts. The older `random_forest.pkl`, `xgboost_model.pkl`, `isolation_forest.pkl`, `transformer_forecaster.pt` and their metadata are retained only for the explicitly selected legacy synthetic demo path; their metadata now marks `legacy_synthetic_demo_only`, and the default live runtime does not load them. Generated synthetic CSVs and local SQLite state are intentionally not pre-populated in the release; the optional demo command creates its own data, and the runtime creates databases as needed.
#   T r u s t - F e d - R e a l - D a t a  
 #   T r u s t - F e d - R e a l - D a t a  
 #   T r u s t - F e d - R e a l - D a t a  
 