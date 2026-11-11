# Privacy

The prototype's federated simulation keeps each logical client's records inside its local loop and transmits parameter deltas to the coordinator. All clients and server execute in one process; this is not secure process isolation, secure transport, or secure aggregation.

Differential privacy is **disabled**. There is no validated privacy accountant, sampling scheme, or privacy guarantee. Do not interpret update clipping alone as DP. A future DP implementation must define whether adjacency is per reading, meter, household, or organization; specify clipping, noise, sampling, composition, epsilon/delta, and repeated-round accounting; and report utility tradeoffs.

Secure aggregation is also not implemented. It would hide individual updates from the coordinator and conflict with trust signals that inspect individual updates unless a compatible protocol is designed. The central validation set is visible to the coordinator and must be governed accordingly.
