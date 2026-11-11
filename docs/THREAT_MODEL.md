# Threat model

## Prototype scope

The experiment simulates cross-silo clients. An attacker may control a configured fraction of clients and flip local labels or manipulate update scale/direction over every simulated round. A client can produce a non-IID local distribution. The coordinator is trusted to run the experiment and can inspect individual updates and its central validation set. Network transport, endpoint access, and raw-record isolation between OS processes are outside this simulator's guarantees.

## Defenses and limits

Updates are checked for finite values and clipped to a configured norm. Coordinate-wise trimmed mean is included as a robust baseline. The provisional HATTA candidate combines validation utility, temporal consistency, norm compliance, trust-weighted aggregation, and a trimmed-mean correction. Update disagreement alone does not lower trust. The current code does not implement cryptographic update authentication, secure aggregation, backdoor attack success measurement, asynchronous stale-update handling, or formal Byzantine guarantees. Trimming can harm benign rare-class clients and is not assumed universally robust.

The web service requires admin authorization for research endpoints and bounds experiment parameters. The existing operational endpoints require a separate security review before production use.
