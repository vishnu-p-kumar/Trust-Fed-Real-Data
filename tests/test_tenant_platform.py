import pytest, hashlib, hmac, json
from src.federated import tenant_platform as tp

@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setenv("TRUSTFED_DB_PATH",str(tmp_path/"tenant.sqlite3"))
    tp.init_db()

def sign(client, round_id, weights, bias, sample_count):
    payload={"client_id":client["client_id"],"round_id":round_id,"weights":[float(x) for x in weights],
             "bias":float(bias),"sample_count":int(sample_count)}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
    key=hashlib.sha256(client["client_secret"].encode()).digest()
    return hmac.new(key,canonical.encode(),hashlib.sha256).hexdigest()

def make_client(name):
    return tp.create_client(organization=name,name=name+" Admin",email=name.lower()+"@example.com",
        username=name.lower(),password="StrongPassword123",region="Karnataka",location="Bengaluru")

def test_admin_created_client_auth_and_secret_is_not_returned_by_listing():
    client=make_client("Utility A")
    assert client["client_id"].startswith("TFG-")
    assert tp.authenticate_client("utility a@example.com","StrongPassword123")["client_id"]==client["client_id"]
    assert tp.authenticate_client("utilitya","wrong") is None
    listed=tp.list_clients()[0]
    assert "secret_hash" not in listed and "client_secret" not in listed

def test_client_status_blocks_login():
    client=make_client("Utility B")
    assert tp.set_client_status(client["client_id"],"suspended")
    assert tp.authenticate_client("utilityb","StrongPassword123") is None
    assert tp.set_client_status(client["client_id"],"active")

def test_two_real_client_updates_are_trust_weighted_and_aggregated():
    a,b=make_client("Utility C"),make_client("Utility D")
    rnd=tp.create_round()["round_id"]
    ra=tp.submit_update_with_secret(a["client_id"],sign(a,rnd,[0.2,0.4],0.1,100),rnd,[0.2,0.4],0.1,100,validation_auc=0.65)
    rb=tp.submit_update_with_secret(b["client_id"],sign(b,rnd,[0.3,0.5],0.2,200),rnd,[0.3,0.5],0.2,200,validation_auc=0.65)
    assert ra["accepted"] and rb["accepted"]
    result=tp.aggregate_round(rnd)
    assert result["accepted"]==2 and result["model_version"]==1
    assert abs(sum(result["client_weights"].values())-1)<1e-9
    assert len(tp.get_global_model()["weights"])==2
    assert tp.list_trust(a["client_id"])

def test_invalid_secret_and_duplicate_update_rejected():
    a=make_client("Utility E"); rnd=tp.create_round()["round_id"]
    with pytest.raises(PermissionError):
        tp.submit_update_with_secret(a["client_id"],"wrong",rnd,[0.1],0.0,5)
    tp.submit_update_with_secret(a["client_id"],sign(a,rnd,[0.1],0.0,5),rnd,[0.1],0.0,5)
    with pytest.raises(ValueError):
        tp.submit_update_with_secret(a["client_id"],sign(a,rnd,[0.1],0.0,5),rnd,[0.1],0.0,5)

def test_audit_hash_chain_verifies():
    make_client("Utility F")
    assert tp.verify_audit_chain()["valid"]


def test_label_poison_marker_rejects_update_and_lowers_round_score():
    client=make_client("Utility Poison")
    clean_round=tp.create_round()["round_id"]
    clean=tp.submit_update_with_secret(client["client_id"],sign(client,clean_round,[-0.1,-0.2],0.0,100),
        clean_round,[-0.1,-0.2],0.0,100,validation_auc=0.72)
    assert clean["accepted"] is True
    poisoned_round=tp.create_round()["round_id"]
    poisoned=tp.submit_update_with_secret(client["client_id"],sign(client,poisoned_round,[0.1,0.2],0.0,200),
        poisoned_round,[0.1,0.2],0.0,200,validation_auc=0.72,poisoned_row_count=60)
    assert poisoned["accepted"] is False
    assert poisoned["poisoning"] == 1.0
    assert poisoned["trust_score"] < clean["trust_score"]
    assert "client_reported_poison_marker" in poisoned["reason"]


def test_low_coordinator_validation_auc_rejects_even_a_valid_signature():
    client=make_client("Utility Low AUC")
    round_id=tp.create_round()["round_id"]
    result=tp.submit_update_with_secret(client["client_id"],sign(client,round_id,[0.1,0.2],0.0,100),
        round_id,[0.1,0.2],0.0,100,validation_auc=0.31)
    assert result["accepted"] is False
    assert result["validation_auc"] == 0.31
    assert result["trust_score"] < 0.55
    assert result["reason"] == "trusted_validation_auc_below_threshold"


def test_clean_scores_are_per_round_and_do_not_increase_from_history():
    client=make_client("Utility Stable Trust")
    scores=[]
    for _ in range(3):
        round_id=tp.create_round()["round_id"]
        result=tp.submit_update_with_secret(client["client_id"],sign(client,round_id,[-0.1,-0.2],0.0,100),
            round_id,[-0.1,-0.2],0.0,100,validation_auc=0.72)
        scores.append(result["trust_score"])
    assert scores[0] == scores[1] == scores[2]

def test_quality_regression_rejects_unmarked_update_without_changing_global_model():
    client=make_client("Utility Model Guard")
    round_id=tp.create_round()["round_id"]
    columns=["voltage","current"]
    submitted=tp.submit_update_with_secret(client["client_id"],sign(client,round_id,[1.0,0.0],0.0,100),
        round_id,[1.0,0.0],0.0,100,validation_auc=0.75,validation_accuracy=0.9,
        feature_columns=columns)
    assert submitted["accepted"] is True
    before=tp.get_global_model()
    def validator(features,weights,bias):
        assert features==columns
        return {"accuracy":0.9,"auc":0.7} if weights[0]==0 else {"accuracy":0.4,"auc":0.3}
    result=tp.aggregate_round(round_id,validator=validator)
    after=tp.get_global_model()
    assert result["status"]=="quality_rejected"
    assert after==before
    trust=tp.list_trust(client["client_id"])[0]
    assert trust["score"] < submitted["trust_score"]
    assert trust["reason"]=="coordinator_model_quality_regression"


def test_dp_is_applied_and_accounted_when_enabled(monkeypatch):
    monkeypatch.setenv("TRUSTFED_DP_ENABLED","1")
    monkeypatch.setenv("TRUSTFED_DP_NOISE_MULTIPLIER","2.0")
    monkeypatch.setenv("TRUSTFED_DP_MAX_EPSILON","100.0")
    a,b=make_client("Utility DP A"),make_client("Utility DP B")
    rnd=tp.create_round()["round_id"]
    tp.submit_update_with_secret(a["client_id"],sign(a,rnd,[0.2,0.4],0.1,100),rnd,[0.2,0.4],0.1,100,validation_auc=0.65)
    tp.submit_update_with_secret(b["client_id"],sign(b,rnd,[0.3,0.5],0.2,100),rnd,[0.3,0.5],0.2,100,validation_auc=0.65)
    result=tp.aggregate_round(rnd)
    assert result["privacy"]["enabled"] is True
    assert result["privacy"]["rounds_accounted"]==1
    with tp.connect() as db:
        row=db.execute("SELECT rounds,epsilon FROM privacy_accounting WHERE singleton=1").fetchone()
    assert row["rounds"]==1 and row["epsilon"]>0
