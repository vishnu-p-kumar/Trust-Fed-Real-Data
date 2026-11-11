# GridSentinel — detailed run guide

This guide covers local development on Windows PowerShell, from environment setup through the dashboard and API. Run commands from the repository root unless a step says otherwise.

GridSentinel has a Python/FastAPI backend and a static HTML/CSS/JavaScript dashboard in `dashboard/`. There is no `package.json` or frontend build step. The FastAPI application also serves the dashboard at `/dashboard`, so the recommended full-app setup keeps the login page and API on one origin.

The default data and theft labels are **synthetic demonstration data**. The supplied CEEW data has no verified theft labels; use it only for the documented consumption forecast and unlabeled analysis. See [`docs/DATASET_CARD.md`](docs/DATASET_CARD.md).

## 1. Check prerequisites and open the repository

Use Python 3.11 for the closest match to the repository's Docker image. Confirm that PowerShell is in the repository root:

```powershell
Get-Location
python --version
```

`Get-Location` shows the active directory. `python --version` checks the interpreter that will run the commands below. If the displayed folder is not the GridSentinel repository, change to it with `Set-Location <repository-path>`.

The frontend is static and does not need Node.js or `npm install`.

## 2. Create and activate a Python environment

Create a virtual environment inside the repository and activate it:

```powershell
python -m venv .venv
..\.venv\Scripts\Activate.ps1
```

The first command creates an isolated Python environment so project packages do not mix with system packages. The second activates it in the current PowerShell window. If script activation is blocked by your PowerShell policy, run the environment's interpreter directly instead, for example `..\.venv\Scripts\python.exe -m pip install -r requirements.txt`, and use that interpreter for later commands.

Install the project dependencies:

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The first command updates `pip`. The second installs the main backend, data, modeling, forecasting, and visualization dependencies. TensorFlow, XGBoost, and geospatial libraries can make installation slower; several model paths have fallbacks when optional libraries are unavailable.

Install test dependencies when you want to run the test suite:

```powershell
python -m pip install -r requirements-test.txt
```

Install optional advanced dependencies only for workflows that need them, such as Optuna optimization:

```powershell
python -m pip install -r requirements-advanced.txt
```

## 3. Set local authentication and runtime configuration

The API requires a session secret of at least 32 characters and an admin password. For local HTTP development, set these variables in the same PowerShell window that will start the API:

```powershell
$env:SMARTGRID_ADMIN_EMAIL = "admin@gmail.com"
$adminPassword = "FinalProject@123"
$env:SMARTGRID_ADMIN_PASSWORD = $adminPassword
Remove-Variable adminPassword
$env:SMARTGRID_SESSION_SECRET = (python -c "import secrets; print(secrets.token_urlsafe(48))")
$env:SMARTGRID_COOKIE_SECURE = "0"
$env:SMARTGRID_CORS_ORIGINS = "http://127.0.0.1:8080,http://localhost:8080,http://127.0.0.1:8000"
```

These commands set the login to admin@gmail.com / FinalProject@123, generate a session signing key, allow the HTTP cookie needed for local development, and list the local browser origins allowed by CORS. The requested admin credentials are also stored in the ignored local `.env` file and remain the same across restarts. PowerShell values override `.env` for that session. `SMARTGRID_COOKIE_SECURE=0` is for local HTTP development; use HTTPS and secure cookies for a deployed service.

`.env.example` is a reference template. The API loads values from the local `.env` file at startup; PowerShell environment variables take precedence. Do not commit the local `.env` file, tokens, or production secrets.

$env:SMARTGRID_ADMIN_EMAIL and $env:SMARTGRID_ADMIN_PASSWORD are fixed to admin@gmail.com and FinalProject@123 in the run commands. The app also reads the local ignored `.env` file, so those credentials persist when you start the API again in a new PowerShell window. The first API launch creates an ignored `users.json` if one is not present.

Other useful settings include:

- `SMARTGRID_UPDATE_INTERVAL`: live replay interval in seconds; the default is 4.
- `SMARTGRID_FULL_SCALE`: set to `1` for the larger API bootstrap data configuration; the default is `0`.
- `SMARTGRID_DEMO_MODE`: enables demo-only alert behavior; leave `0` for research-oriented runs.
- `SMARTGRID_ENABLE_ALERTS`: enables periodic alert/report behavior; leave `0` for a quiet local run.
- `OPENWEATHER_API_KEY`: optional weather integration key.

Set any of them in PowerShell before starting the process, for example:

```powershell
$env:SMARTGRID_UPDATE_INTERVAL = "4"
$env:SMARTGRID_FULL_SCALE = "0"
$env:SMARTGRID_DEMO_MODE = "0"
$env:SMARTGRID_ENABLE_ALERTS = "0"
```

## 4. Generate the synthetic demo data and models

### Quick smoke run

Use this smaller run to check the generator and model-training pipeline without creating a report or sample response files:

```powershell
python run_project.py --num-meters 20 --days 7 --forecast-epochs 1 --skip-report --skip-sample-export
```

It generates seven days for 20 synthetic meters, trains the anomaly, theft-classification, and forecasting models with one forecasting epoch, and writes the heatmap and model/data artifacts. `--skip-report` avoids the PDF report, and `--skip-sample-export` avoids reference API payload files. This is a smoke test; its synthetic scores are not evidence of real-world theft detection.

### Normal bootstrap

For the default local demonstration, run:

```powershell
python run_project.py
```

This uses the default 500-meter, 60-day synthetic configuration. It generates data, writes meter and pole catalogs, trains anomaly/theft/forecast models, builds the heatmap, exports sample outputs, and writes the daily report. This takes longer than the smoke run.

The API checks for the expected default artifacts. If it finds missing files or artifacts from a different-size generator run, startup can regenerate the default data and models. Therefore, the quick smoke output may be replaced when the API starts.

### Useful `run_project.py` options

| Option | Purpose |
|---|---|
| `--num-meters N` | Override the number of synthetic meters. |
| `--days N` | Override the number of simulated days. |
| `--full-scale` | Use the larger 1,000-meter, 365-day configuration. This requires substantially more time and storage. |
| `--forecast-epochs N` | Set forecasting training epochs. |
| `--skip-training` | Generate data but skip model training and the downstream prediction/report workflow. |
| `--skip-report` | Skip the daily PDF report. |
| `--skip-sample-export` | Skip sample API output files. |
| `--optimize-models` | Run optional Optuna hyperparameter optimization before model training. Requires the advanced dependency set. |
| `--optimization-trials N` | Set the number of Optuna trials; only applies with `--optimize-models`. |
| `--start-api` | Bootstrap using this command's generation options, then start the API on `127.0.0.1:8000`. |

Examples:

```powershell
python run_project.py --skip-training
python run_project.py --num-meters 100 --days 30 --forecast-epochs 2 --skip-report --skip-sample-export
python run_project.py --optimize-models --optimization-trials 8
```

The first generates data only. The second runs a medium-sized training/demo workflow. The third enables the optional tuning pass and runs eight trials.

## 5. Run the tests

From the repository root:

```powershell
python -m pytest -q
```

This runs the backend, data pipeline, model, API, dashboard-workflow, and federated research tests. A passing suite verifies covered behavior; it does not establish real-world theft-detection performance. To run only the CEEW ingestion and forecast tests:

```powershell
python -m pytest tests/test_ceew_dataset.py -q
```

## 6. Start the API and open the full dashboard

### Option A: bootstrap and start in one command

After setting the environment variables in Step 3, run:

```powershell
python run_project.py --start-api
```

This generates the default synthetic dataset, trains models, writes runtime artifacts, and then launches the API. The process stays attached to the terminal; use `Ctrl+C` to stop it.

### Option B: start the API after bootstrap

If the expected data and model artifacts already exist, start only the API:

```powershell
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

`uvicorn` runs the FastAPI application. Its startup checks artifacts and bootstraps missing or mismatched defaults, so the first API launch can take longer. Keep this terminal open while using the dashboard.

The API also serves the dashboard files on the same origin. Open:

- Login: `http://127.0.0.1:8000/login`
- Dashboard files: `http://127.0.0.1:8000/dashboard/`
- Health check: `http://127.0.0.1:8000/health`
- Interactive API documentation: `http://127.0.0.1:8000/docs`

Check API health from another PowerShell window:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health | ConvertTo-Json -Depth 6
```

This requests the health payload and prints the status and artifact checks. A `degraded` status means one or more required generated artifacts are missing; inspect the response and rerun `python run_project.py` if needed.

## 7. Serve the static dashboard separately (preview mode)

The dashboard can also be served as static files in a second terminal:

```powershell
python -m http.server 8080 --directory dashboard
```

This serves the HTML, CSS, and JavaScript files at `http://127.0.0.1:8080`. The dashboard's data API base defaults to `http://127.0.0.1:8000`; it can be changed in the dashboard's API Base URL control. The current login/admin scripts use same-origin authentication calls, so use the API-served login at `http://127.0.0.1:8000/login` for the complete authenticated workflow. The separate static server is useful for previewing files; it does not replace the API.

## 8. Run the federated synthetic research experiment

The federated theft-classification simulator uses a generated labeled fixture; it is separate from the CEEW unlabeled real-consumption experiment.

Run the calibrated trust-validation study:

```powershell
python scripts/run_trust_validation.py
```

This runs the multi-scenario synthetic study and writes `reports/research_runs/trust_validation_20261028.json`. Its theft labels are simulated, and its results are not real-meter performance claims.

Run one smaller experiment directly:

```powershell
python -c "from src.federated.experiment import run_experiment; result = run_experiment({'samples': 400, 'features': 10, 'clients': 4, 'rounds': 3, 'local_epochs': 2, 'partition': 'severe', 'attack': 'sign', 'seed': 42}); print(result['metrics'])"
```

This runs a four-client, three-round severe non-IID sign-attack simulation and prints the measured model metrics. No attack success rate is defined for this untargeted sign-flip experiment.

## 9. Process and forecast the supplied CEEW data (optional)

The CEEW files are not required to run the synthetic demo. They contain no verified theft labels. Keep raw files outside Git; `data/raw/ceew/` is ignored. Set the directory to wherever you stored the files:

```powershell
$ceewDir = "C:\path\to\dataverse_files"
```

Profile all eight supplied CSVs without writing normalized readings:

```powershell
python scripts/prepare_ceew_dataset.py --profile-only --chunksize 200000 --output reports/research_runs/ceew_profile --input `
  "$ceewDir\CEEW - Smart meter data Bareilly 2020.csv" `
  "$ceewDir\CEEW - Smart meter data Bareilly 2021.csv" `
  "$ceewDir\CEEW - Smart meter data Mathura 2019.csv" `
  "$ceewDir\CEEW - Smart meter data Mathura 2020.csv" `
  "$ceewDir\SM Cleaned Data BR Aggregated.csv" `
  "$ceewDir\SM Cleaned Data BR2019.csv" `
  "$ceewDir\SM Cleaned Data MH Aggregated.csv" `
  "$ceewDir\SM Cleaned Data MH2021.csv"
```

The command streams the source files, records hashes and data-quality counts, and writes `reports/research_runs/ceew_profile/ceew_manifest.json`. It does not modify or copy the raw files.

Normalize the two daily aggregate CSVs into chunked gzip files under the ignored processed-data folder:

```powershell
python scripts/prepare_ceew_dataset.py --output data/processed/ceew --input `
  "$ceewDir\SM Cleaned Data BR Aggregated.csv" `
  "$ceewDir\SM Cleaned Data MH Aggregated.csv"
```

Run the five-seed daily consumption forecast comparison:

```powershell
python scripts/run_ceew_forecast.py `
  --input "data/processed/ceew/daily_aggregate/SM Cleaned Data BR Aggregated.normalized.csv.gz" `
         "data/processed/ceew/daily_aggregate/SM Cleaned Data MH Aggregated.normalized.csv.gz" `
  --interval 1D --clients 4 --rounds 3 --local-epochs 5 `
  --learning-rate-candidates 0.01 0.03 0.05 0.1 `
  --seeds 42 43 44 45 46 --output reports/research_runs/ceew_forecast.json
```

The runner selects the learning rate using validation FedAvg MAE, evaluates a final chronological test period, and reports forecast metrics for centralized, local-only, FedAvg, trimmed mean, and persistence baselines. The seeds vary meter-to-client assignment over the same time split, so uncertainty describes assignment sensitivity rather than population sampling. The residual threshold is an unlabeled anomaly proxy, not a theft result. See [`docs/DATASET_CARD.md`](docs/DATASET_CARD.md) for measured results and limitations.

For a two-client geographic non-IID pilot, add `--client-partition location --clients 2 --seed 42` and choose a separate output path. This assigns all Mathura meters to one client and all Bareilly meters to another; it is a single-seed pilot.

## 10. Stop services and common issues

- Stop the API or static file server with `Ctrl+C` in its terminal.
- If the API cannot create a session, check that `SMARTGRID_SESSION_SECRET` is at least 32 characters and that the admin email/password environment variables are set in the same terminal that launched the API.
- If login works on the API-served dashboard but not on port 8080, use `http://127.0.0.1:8000/login`; the authenticated pages expect the API and frontend to share an origin.
- If the dashboard cannot reach API data, confirm the API is running at `http://127.0.0.1:8000/health` and check the API Base URL setting.
- If the health response is degraded, run `python run_project.py` to regenerate the normal synthetic data and model artifacts.
- If port 8000 or 8080 is occupied, stop the other process or choose an available port. If you change the API port, update the dashboard API Base URL and the CORS origins where cross-origin use is intended.
- If an optional library is unavailable, the main workflow may use a fallback model. Install the matching requirements only if you need that optional model path.

## Commands to start the backend and frontend

Open two PowerShell windows at the repository root. In the backend window, set the local authentication variables from Step 3, then run one of these:

```powershell
# Bootstrap data/models, then start FastAPI:
python run_project.py --start-api

# Or, if the expected artifacts already exist, start FastAPI directly:
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

The API process also serves the full authenticated frontend at `http://127.0.0.1:8000/login` and `http://127.0.0.1:8000/dashboard/`; no separate frontend build or server is needed for the complete app.

In the second window, this command starts a separate static frontend preview on port 8080:

```powershell
python -m http.server 8080 --directory dashboard
```

Use the API-served frontend on port 8000 for login and the complete authenticated workflow. The port-8080 server only serves static files; it does not run the backend.

## Copy-paste commands to run the complete app (Windows PowerShell)

Open PowerShell in the repository root (the folder containing `run_project.py`) and paste this block. It creates a virtual environment, installs the project requirements, sets local login settings, generates demo data and models, then starts the FastAPI server on port 8002. The API also serves the authenticated dashboard, so you do not need a separate frontend server.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:SMARTGRID_ADMIN_EMAIL = "admin@gmail.com"
$env:SMARTGRID_ADMIN_PASSWORD = "FinalProject@123"
$env:SMARTGRID_SESSION_SECRET = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(48))")
$env:SMARTGRID_COOKIE_SECURE = "0"
$env:SMARTGRID_CORS_ORIGINS = "http://127.0.0.1:8002,http://localhost:8002"
$env:SMARTGRID_UPDATE_INTERVAL = "4"
$env:SMARTGRID_FULL_SCALE = "0"
$env:SMARTGRID_DEMO_MODE = "0"
$env:SMARTGRID_ENABLE_ALERTS = "0"
.\.venv\Scripts\python.exe run_project.py
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8002
```

Keep this PowerShell window open while using the app. Open `http://127.0.0.1:8002/login` and sign in with the admin email and password you entered. The client portal is at `http://127.0.0.1:8002/client`; admin and inspectors can use the same login page. The API health endpoint is `http://127.0.0.1:8002/health`.

The initial `run_project.py` step trains the project models and may take several minutes. Later, once generated data and models are present, you can start the app without regenerating them by running these commands in the same configured PowerShell window:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8002
```

Stop the app with `Ctrl+C`. The commands use port 8002 to avoid colliding with services already using ports 8000 and 8001 on this machine. If port 8002 is also occupied, replace `8002` consistently in the Uvicorn command, browser URLs, and `SMARTGRID_CORS_ORIGINS`.
