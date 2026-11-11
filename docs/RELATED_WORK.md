# Related work to verify and compare

- McMahan et al. (2017), “Communication-Efficient Learning of Deep Networks from Decentralized Data,” AISTATS / PMLR 54:1273–1282. [PMLR paper](https://proceedings.mlr.press/v54/mcmahan17a.html). FedAvg baseline.
- Blanchard et al. (2017), “Machine Learning with Adversaries: Byzantine Tolerant Gradient Descent,” NeurIPS 30. [NeurIPS paper](https://papers.neurips.cc/paper/2017/hash/f4b9ec30ad9f68f89b29639786cb62ef-Abstract.html). Krum's Byzantine assumptions must be considered before adapting it to heterogeneous utility clients.
- Cao et al. (2021), “FLTrust: Byzantine-robust Federated Learning via Trust Bootstrapping,” NDSS. [NDSS paper](https://www.ndss-symposium.org/wp-content/uploads/ndss2021_6C-2_24434_paper.pdf). Trust uses a clean root dataset, creating governance and representativeness assumptions.
- Wen et al. (2025), “A privacy-preserving heterogeneous federated learning framework with class imbalance learning for electricity theft detection,” *Applied Energy* 378, 124789. DOI [10.1016/j.apenergy.2024.124789](https://doi.org/10.1016/j.apenergy.2024.124789). Direct electricity-theft FL work.
- Wei, Gong & Cao (2026), “Robust federated learning for detecting false data injection attacks in advanced metering infrastructure under non-IID data,” *Scientific Reports*, published 23 October 2026. DOI [10.1038/s41598-026-72303-6](https://doi.org/10.1038/s41598-026-72303-6). Adjacent AMI threat-detection work; its target is false-data injection rather than theft labels.

This is a starting bibliography, not a systematic review. HATTA novelty remains unverified. Compare current electricity-theft FL, robust FL, trust-aware FL, non-IID optimization, poisoning, DP, and secure-aggregation literature before publication.
