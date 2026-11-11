# Reproducibility

The local experiment accepts an explicit seed and writes configuration, per-round logs, metrics, and final model parameters under its output directory. Preprocessing scaler fitting occurs on training rows. Synthetic fixtures and client partitions are seeded.

For reproduction, record the repository revision, Python and dependency versions, data hash, all run parameters, and hardware. Run the tests with `python -m pytest -q`; run the example with `python -c "from src.federated.experiment import run_experiment; print(run_experiment())"`. The repository does not yet pin a lockfile, save full environment manifests, support checkpoint resume, or aggregate multiple seed runs; those are outstanding reproducibility tasks.
