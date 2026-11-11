# Labeled theft datasets (not bundled)

This folder is reserved for externally obtained, properly licensed labeled datasets. Do not put private utility/customer data in version control.

## Recommended public research benchmark

The State Grid Corporation of China (SGCC) Electricity Theft Detection dataset is a commonly used real-consumption benchmark with theft labels reported from utility inspections. Public dataset record: https://ieee-pes-data-sharing.org/datasets/detail/663b8e0e-3ace-48f8-b983-4cb59b39fa6f . The record lists the license as N/A, so confirm redistribution and usage terms before using it outside research. It is not Indian data; performance on it does not establish performance for Indian DISCOMs. Labels can still contain inspection/ascertainment bias.

## Indian smart-meter data

CEEW's Mathura/Bareilly smart-meter data is an India-specific consumption/supply dataset, but it does not include verified theft labels. Dataset record: https://doi.org/10.7910/DVN/GOCHJH . Use it for consumption profiling and forecasting, not supervised theft-classification claims.

## Expected steps

1. Download data only from a source whose license permits your intended use.
2. Keep the raw file here, but do not commit it.
3. Create a provenance JSON based on `docs/ROADMAP_IMPLEMENTATION.md`.
4. Run `scripts/validate_theft_dataset.py`.
5. Run `scripts/evaluate_theft_models.py` and record the exact dataset checksum with the metrics.
6. Keep synthetic and real-source evaluation results separate.

Structural checks cannot prove label truth. For an independently verified dataset, retain evidence from the publisher/utility describing the inspection-derived label process.
