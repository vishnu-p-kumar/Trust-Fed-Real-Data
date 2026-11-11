# GridSentinel architecture

## Current application architecture

- **Presentation:** static HTML/CSS/JavaScript under `dashboard/`; served by FastAPI at `/dashboard`.
- **API/application:** `api/main.py` provides REST endpoints, authenticated sessions, a WebSocket live stream, simulation lifecycle, and orchestration.
- **Analytics:** `src/` provides preprocessing, feature engineering, theft/anomaly scoring, forecasting, explainability, risk scoring, pole monitoring, alerts, reports, and drift analysis.
- **Federated research:** `src/federated/` runs an in-process simulation with client partitions, local model updates, FedAvg/trimmed mean/trust weighting, and attack experiments. It is not a network-isolated multi-utility deployment.
- **Persistence:** datasets and model artifacts are files; operational tables are written to SQLite through `utils/helpers.py`. `src/jobs/sqlite_queue.py` adds a durable single-host queue primitive, but the app's long-running workflows are not yet all routed through it.
- **Testing/operations:** `tests/`, `scripts/`, `docs/`, Docker files, and `run_project.py` cover automated tests, research experiments, model/data generation and local setup.

## Main data flow

```text
Meter CSV / synthetic generator / optional utility ingestion
    -> validation and preprocessing
    -> feature engineering
    -> anomaly detection + theft classifier + demand forecast
    -> risk scoring and explanations
    -> FastAPI endpoints / WebSocket
    -> dashboard, alert review, inspector assignment and completion
    -> SQLite operational snapshots and file-based model/report artifacts
```

## Target production architecture (not fully deployed in this repository)

```text
Smart-meter ingestion -> schema/quality gate -> durable event queue
    -> feature service -> versioned model services -> risk/explanation service
    -> case/alert workflow -> dashboard and operator review

Identity provider/RBAC | PostgreSQL operational store | time-series store
Object storage/model registry | central logs/metrics/audit | CI/CD and model monitoring

Independent utility clients -> authenticated FL coordinator
    -> vetted secure aggregation + accounted differential privacy
```

Do not interpret the target architecture as a claim that the services above are already independently deployed. The current system is primarily a single-process FastAPI app. PostgreSQL migration, multi-worker queue integration, network-isolated federated clients, formal multi-round privacy accounting, and production operations remain release gates.
