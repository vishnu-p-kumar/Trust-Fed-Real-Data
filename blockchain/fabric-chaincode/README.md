# Hyperledger Fabric chaincode starter

This chaincode records immutable commitments (round/client/update hash/model version) in a Fabric world state. It does not store raw meter data or model weights.

This is source code only. A real Fabric deployment still needs peer/orderer organizations, MSP/CA identities, channel creation, endorsement policy, TLS, chaincode packaging/installation/approval/commit, governance, monitoring, backup and security review. The local SQLite hash-linked audit log remains the active application ledger until that network is provisioned and integrated.
