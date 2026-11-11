# GitHub Actions Used In This Project

This project uses GitHub Actions for Continuous Integration. The workflow automatically checks the project whenever code is pushed to GitHub or a pull request is created.

Workflow file:

```text
.github/workflows/ci.yml
```

## 1. What Is GitHub Actions?

GitHub Actions is a CI/CD automation tool provided by GitHub.

CI means Continuous Integration. In this project, CI is used to:

- automatically set up the project environment
- install test dependencies
- run the test suite
- detect errors before merging or accepting changes

## 2. Workflow Name

The workflow is named:

```yaml
name: CI
```

This name appears in the GitHub Actions tab.

## 3. When The Workflow Runs

The workflow runs on:

```yaml
on:
  push:
  pull_request:
```

This means GitHub Actions runs when:

- code is pushed to the repository
- a pull request is opened or updated

## 4. Job Used

The workflow has one job:

```yaml
jobs:
  tests:
```

The job name is `tests`.

Its purpose is to run the automated test suite for the project.

## 5. Runner Used

The job runs on:

```yaml
runs-on: ubuntu-latest
```

This means GitHub creates a temporary Ubuntu Linux machine to run the workflow.

## 6. Actions Used

Two official GitHub Actions are used in this workflow.

### 6.1 `actions/checkout@v6`

Used in:

```yaml
- name: Checkout
  uses: actions/checkout@v6
```

Purpose:

- downloads the repository code into the GitHub Actions runner
- makes files like `requirements-test.txt`, `src/`, `api/`, and `tests/` available to later steps

Why it is needed:

Without checkout, the runner would not have the project files, so it could not install dependencies or run tests.

### 6.2 `actions/setup-python@v6`

Used in:

```yaml
- name: Set up Python
  uses: actions/setup-python@v6
  with:
    python-version: "3.11"
```

Purpose:

- installs and configures Python 3.11 on the runner
- makes the `python` command available for the next steps

Why Python 3.11 is used:

- the project is a Python-based ML and FastAPI project
- Python 3.11 is stable and compatible with the project dependencies
- using a fixed Python version makes CI more predictable

## 7. Commands Used In The Workflow

Apart from actions, the workflow also runs shell commands.

### 7.1 Install Test Dependencies

Command:

```yaml
- name: Install test dependencies
  run: python -m pip install -r requirements-test.txt
```

Purpose:

- installs packages needed for testing
- reads dependencies from `requirements-test.txt`

Typical packages include:

- `pytest`
- `httpx`
- API testing dependencies
- project test utilities

Why `python -m pip` is used:

- it ensures pip belongs to the Python version configured by `actions/setup-python`
- it avoids confusion when multiple Python versions exist

### 7.2 Run Tests

Command:

```yaml
- name: Run tests
  run: python -m pytest -q
```

Purpose:

- runs all automated tests in the `tests/` folder
- checks API behavior, data pipeline logic, model utilities, forecasting, inspector workflow, and theft detection logic

Why `python -m pytest` is used:

- it runs pytest using the selected Python interpreter
- it is more reliable than calling `pytest` directly

Why `-q` is used:

- `-q` means quiet mode
- it keeps GitHub Actions logs shorter and easier to read

## 8. Full Workflow

Current workflow:

```yaml
name: CI

on:
  push:
  pull_request:

jobs:
  tests:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v6

      - name: Set up Python
        uses: actions/setup-python@v6
        with:
          python-version: "3.11"

      - name: Install test dependencies
        run: python -m pip install -r requirements-test.txt

      - name: Run tests
        run: python -m pytest -q
```

## 9. What This Workflow Checks

The workflow checks whether the project tests pass successfully.

The tests cover areas such as:

- API health and endpoint responses
- data generation and preprocessing
- theft detection probability calibration
- anomaly and risk scoring behavior
- forecasting fallback behavior
- sample output generation
- inspector dashboard workflow
- pole monitoring payloads

## 10. Why GitHub Actions Is Useful In This Project

GitHub Actions is useful because:

- it catches code errors automatically
- it checks that tests pass on a clean machine
- it prevents broken code from being merged silently
- it proves that the project can be installed and tested outside the local computer
- it helps during project evaluation because the test status is visible on GitHub

## 11. Error Fixed In This Project

Earlier, the workflow had an incorrect working directory:

```yaml
working-directory: electricity_theft_detection
```

That folder did not exist in the GitHub runner, so GitHub Actions failed with:

```text
No such file or directory
```

The fix was to remove the incorrect working directory so commands run from the repository root.

## 12. Possible Future GitHub Actions Improvements

This project can be improved further by adding:

- dependency caching for faster workflow runs
- linting with `ruff` or `flake8`
- formatting checks with `black`
- type checking with `mypy`
- Docker image build checks
- test coverage reports
- deployment workflow for API hosting
- scheduled workflow to run tests daily

## 13. Short Interview Answer

If asked "Is GitHub Actions used in this project?", you can answer:

Yes. This project uses GitHub Actions for Continuous Integration. The workflow is defined in `.github/workflows/ci.yml`. It runs on every push and pull request. It checks out the repository using `actions/checkout@v6`, sets up Python 3.11 using `actions/setup-python@v6`, installs test dependencies from `requirements-test.txt`, and runs the test suite using `python -m pytest -q`. This helps ensure that the code works correctly before changes are merged.
