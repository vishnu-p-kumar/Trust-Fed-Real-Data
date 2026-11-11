import numpy as np
import pytest
from src.federated.scaffold import scaffold_gradient, update_client_control
from src.security.privacy_accountant import GaussianRDPAccountant
from src.security.secure_aggregation import masked_sum
from src.federated.blockchain_ledger import HashLinkedLedger
from src.federated.monitoring import population_stability_index, binary_calibration_error
from src.investigation.case_manager import CaseManager

def test_scaffold_primitives():
    np.testing.assert_allclose(scaffold_gradient([1,2],[.1,.2],[.3,.4]),[1.2,2.2])
    result=update_client_control([0,0],[1,1],[2,2],.5,2)
    np.testing.assert_allclose(result,[1,1])

def test_rdp_accountant_monotonic():
    a=GaussianRDPAccountant(); a.step(2); e1=a.epsilon(1e-5); a.step(2)
    assert a.epsilon(1e-5)>e1 and a.steps==2

def test_pairwise_masks_cancel():
    updates={"a":np.array([1.,2.]),"b":np.array([3.,4.]),"c":np.array([-1.,1.])}
    np.testing.assert_allclose(masked_sum(updates,secret=b"demo",round_id="r1"),sum(updates.values()))

def test_ledger_detects_tamper(tmp_path):
    ledger=HashLinkedLedger(tmp_path/"ledger.db"); ledger.append({"event":"create"}); ledger.append({"event":"round"})
    assert ledger.verify()
    import sqlite3
    with sqlite3.connect(ledger.path) as db: db.execute("UPDATE blocks SET payload='{}' WHERE height=0")
    assert not ledger.verify()

def test_drift_and_calibration():
    assert population_stability_index(np.arange(100),np.arange(100)) < 1e-8
    assert binary_calibration_error([.1,.9],[0,1]) < .11

def test_case_workflow(tmp_path):
    cases=CaseManager(tmp_path/"cases.db")
    case=cases.create("M-1","Unusual night load",priority="high",actor="analyst")
    assert case["status"]=="open"
    updated=cases.update(case["case_id"],status="investigating",assignee="team-a",note="Review interval data")
    assert updated["assignee"]=="team-a" and len(updated["events"])==2
    assert cases.list(status="investigating")[0]["meter_id"]=="M-1"

def test_invalid_case_status_rejected(tmp_path):
    cases=CaseManager(tmp_path/"cases.db")
    case=cases.create("M-1","Review")
    with pytest.raises(ValueError): cases.update(case["case_id"],status="bogus")


def test_secure_aggregation_session_rejects_round_replay():
    from src.security.secure_aggregation import SecureAggregationSession
    keys = {("a", "b"): b"a" * 32, ("a", "c"): b"b" * 32, ("b", "c"): b"c" * 32}
    session = SecureAggregationSession(keys)
    updates = {"a": np.array([1.0, 2.0]), "b": np.array([3.0, 4.0]), "c": np.array([5.0, 6.0])}
    result = session.aggregate(updates, round_id="round-1")
    np.testing.assert_allclose(result["aggregate"], np.array([9.0, 12.0]), atol=1e-8)
    with pytest.raises(ValueError, match="replay"):
        session.aggregate(updates, round_id="round-1")
