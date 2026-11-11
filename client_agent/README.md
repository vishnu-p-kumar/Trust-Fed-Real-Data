# TrustFedGrid independent client agent

Each utility/site runs this agent on a machine that can access its own local meter CSV. The CSV is read locally; only model parameters, feature names, sample count, round ID, and authenticated update metadata are sent to the coordinator. The coordinator independently scores each submitted model on its labeled reference sample before accepting it.

## Requirements
`pip install numpy pandas requests`

## Prepare the coordinator
1. Start the API and sign in as administrator.
2. Open `/dashboard/admin/clients.html` and create a client organization.
3. Copy the generated client-agent secret immediately; it is shown only once.
4. Create a federated training round and copy its round ID.

## Run at the client site
```bash
python client_agent.py --api http://COORDINATOR_HOST:8000 \
  --client-id TFG-CLIENTID --password 'CLIENT_LOGIN_PASSWORD' \
  --client-secret 'ONE_TIME_AGENT_SECRET' --csv ./local_meter_data.csv \
  --label is_theft --features voltage,current,power,consumption_kwh,power_factor \
  --round-id R-ROUNDID --epochs 20
```

All clients in a given global model must use the same feature names, order, and units. This baseline supports `voltage`, `current`, `power`, `consumption_kwh`, and `power_factor` with a shared fixed feature transform. Both binary label classes (0=normal, 1=theft) must be present locally. It uses class-balanced logistic-regression training initialized from the current global parameters. This is a practical Phase-II baseline, not a replacement for the project's existing theft model pipeline.

## Security notes
- Do not commit credentials or client secrets.
- Use HTTPS in deployments; do not send credentials over public HTTP.
- Client secrets are stored as SHA-256 verifiers, not plaintext.
- This agent uses an authenticated HMAC credential for update submission. It is not a complete secure-aggregation protocol.
- An `is_poisoned` CSV column is treated as a client-reported warning and causes that update to be rejected. The coordinator also validates model quality independently; the marker itself is not cryptographically attested.
- The coordinator sees model parameters. Model updates can leak information; deploy an independently reviewed secure-aggregation and differential-privacy protocol before handling real customer data.
