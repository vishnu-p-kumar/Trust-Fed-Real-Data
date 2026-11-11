"""Persistent multi-tenant client registry and trust-aware federated coordinator.

The coordinator stores account metadata, model updates and audit metadata only.
Raw client CSV data is processed by the separately deployed client agent.
"""
from __future__ import annotations
import hashlib, hmac, json, math, os, secrets, sqlite3, time, uuid
from pathlib import Path
from typing import Any

def db_path() -> Path:
    configured = os.getenv("TRUSTFED_DB_PATH")
    if configured:
        path = Path(configured)
    else:
        path = Path(__file__).resolve().parents[2] / "database" / "trustfed_phase2.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

def connect():
    con=sqlite3.connect(db_path(), timeout=30)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS clients(
          client_id TEXT PRIMARY KEY, organization TEXT NOT NULL, name TEXT NOT NULL,
          email TEXT NOT NULL UNIQUE, username TEXT NOT NULL UNIQUE,
          password_salt TEXT NOT NULL, password_hash TEXT NOT NULL,
          secret_hash TEXT NOT NULL, region TEXT NOT NULL DEFAULT '',
          location TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'active',
          created_at REAL NOT NULL, last_seen REAL
        );
        CREATE TABLE IF NOT EXISTS client_datasets(
          dataset_id TEXT PRIMARY KEY, client_id TEXT NOT NULL REFERENCES clients(client_id),
          filename TEXT NOT NULL, sha256 TEXT NOT NULL, row_count INTEGER NOT NULL,
          feature_columns_json TEXT NOT NULL, label_column TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS client_trust(
          id INTEGER PRIMARY KEY AUTOINCREMENT, client_id TEXT NOT NULL REFERENCES clients(client_id),
          round_id TEXT NOT NULL, score REAL NOT NULL, integrity REAL NOT NULL,
          similarity REAL NOT NULL, validation REAL NOT NULL, validation_accuracy REAL NOT NULL DEFAULT 0.0,
          poisoning REAL NOT NULL,
          weight REAL NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS federated_rounds(
          round_id TEXT PRIMARY KEY, status TEXT NOT NULL, model_version INTEGER NOT NULL,
          participants INTEGER NOT NULL DEFAULT 0, accepted INTEGER NOT NULL DEFAULT 0,
          rejected INTEGER NOT NULL DEFAULT 0, created_at REAL NOT NULL, completed_at REAL
        );
        CREATE TABLE IF NOT EXISTS model_updates(
          update_id TEXT PRIMARY KEY, round_id TEXT NOT NULL, client_id TEXT NOT NULL,
          update_hash TEXT NOT NULL, signature_valid INTEGER NOT NULL,
          accepted INTEGER NOT NULL, trust_score REAL, aggregation_weight REAL,
          sample_count INTEGER NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS audit_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL,
          actor_id TEXT NOT NULL, payload_json TEXT NOT NULL, previous_hash TEXT NOT NULL,
          event_hash TEXT NOT NULL UNIQUE, created_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS global_model(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), version INTEGER NOT NULL,
          weights_json TEXT NOT NULL, bias REAL NOT NULL, updated_at REAL NOT NULL,
          feature_columns_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS federated_update_payloads(
          update_id TEXT PRIMARY KEY REFERENCES model_updates(update_id) ON DELETE CASCADE,
          weights_json TEXT NOT NULL, bias REAL NOT NULL, feature_columns_json TEXT NOT NULL DEFAULT '[]'
        );
        CREATE TABLE IF NOT EXISTS privacy_accounting(
          singleton INTEGER PRIMARY KEY CHECK(singleton=1), orders_json TEXT NOT NULL,
          rdp_json TEXT NOT NULL, rounds INTEGER NOT NULL DEFAULT 0, epsilon REAL NOT NULL DEFAULT 0,
          delta REAL NOT NULL, updated_at REAL NOT NULL
        );
        """)
        # Add the validation schema to databases created by earlier app versions.
        migrations = {
            "client_trust": ("validation_accuracy", "REAL NOT NULL DEFAULT 0.0"),
            "global_model": ("feature_columns_json", "TEXT NOT NULL DEFAULT '[]'"),
            "federated_update_payloads": ("feature_columns_json", "TEXT NOT NULL DEFAULT '[]'"),
        }
        for table, (column, definition) in migrations.items():
            existing={row[1] for row in c.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        c.execute("INSERT OR IGNORE INTO global_model(singleton,version,weights_json,bias,updated_at) VALUES(1,0,'[]',0,?)",(time.time(),))

def _password(password: str, salt: bytes|None=None):
    salt=salt or secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,240000)
    return salt.hex(),digest.hex()

def _verify(password,salt,digest):
    return hmac.compare_digest(_password(password,bytes.fromhex(salt))[1],digest)

def audit(c, event_type, actor_id, payload):
    row=c.execute("SELECT event_hash FROM audit_events ORDER BY id DESC LIMIT 1").fetchone()
    previous=row["event_hash"] if row else "0"*64
    created=time.time()
    body=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str)
    event_hash=hashlib.sha256(f"{previous}|{event_type}|{actor_id}|{created:.6f}|{body}".encode()).hexdigest()
    c.execute("INSERT INTO audit_events(event_type,actor_id,payload_json,previous_hash,event_hash,created_at) VALUES(?,?,?,?,?,?)",
              (event_type,actor_id,body,previous,event_hash,created))
    return event_hash

def create_client(*,organization,name,email,username,password,region="",location=""):
    client_id="TFG-"+uuid.uuid4().hex[:10].upper()
    salt,pwhash=_password(password)
    secret=secrets.token_urlsafe(36)
    with connect() as c:
        c.execute("""INSERT INTO clients(client_id,organization,name,email,username,password_salt,password_hash,secret_hash,region,location,status,created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?, 'active',?)""",(client_id,organization,name,email.lower(),username.lower(),salt,pwhash,
        hashlib.sha256(secret.encode()).hexdigest(),region,location,time.time()))
        audit(c,"client.created",client_id,{"organization":organization,"email":email.lower()})
    return {"client_id":client_id,"organization":organization,"name":name,"email":email.lower(),
            "username":username.lower(),"region":region,"location":location,"status":"active",
            "client_secret":secret,"created_at":time.time()}

def list_clients():
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT client_id,organization,name,email,username,region,location,status,created_at,last_seen
          FROM clients ORDER BY created_at DESC""")]

def authenticate_client(identifier,password):
    with connect() as c:
        r=c.execute("SELECT * FROM clients WHERE username=? OR email=? OR client_id=?",
                    (identifier.lower(),identifier.lower(),identifier.upper())).fetchone()
        if not r or r["status"]!="active" or not _verify(password,r["password_salt"],r["password_hash"]): return None
        c.execute("UPDATE clients SET last_seen=? WHERE client_id=?",(time.time(),r["client_id"]))
        return {"id":r["client_id"],"client_id":r["client_id"],"username":r["username"],
                "email":r["email"],"name":r["name"],"organization":r["organization"],
                "role":"client","region":r["region"],"location":r["location"]}

def client_profile(client_id):
    with connect() as c:
        r=c.execute("""SELECT client_id,organization,name,email,username,region,location,status,created_at,last_seen
        FROM clients WHERE client_id=?""",(client_id,)).fetchone()
        return dict(r) if r else None

def set_client_status(client_id,status):
    if status not in {"active","suspended"}: raise ValueError("status must be active or suspended")
    with connect() as c:
        cur=c.execute("UPDATE clients SET status=? WHERE client_id=?",(status,client_id))
        if cur.rowcount: audit(c,"client.status_changed",client_id,{"status":status})
        return bool(cur.rowcount)

def get_global_model():
    with connect() as c:
        r=c.execute("SELECT * FROM global_model WHERE singleton=1").fetchone()
        return {"version":r["version"],"weights":json.loads(r["weights_json"]),"bias":r["bias"],
                "feature_columns":json.loads(r["feature_columns_json"] or "[]")}

def _client_secret(c,client_id):
    r=c.execute("SELECT secret_hash,status FROM clients WHERE client_id=?",(client_id,)).fetchone()
    return r

def submit_update(client_id, round_id, weights, bias, sample_count, update_hash, signature):
    # HMAC key material is derived from the client-specific secret. Secret itself is never stored.
    import numpy as np
    vector=np.asarray(weights,dtype=float)
    if vector.ndim!=1 or vector.size<1 or vector.size>10000 or not np.isfinite(vector).all() or not math.isfinite(float(bias)):
        raise ValueError("model update must contain finite numeric weights and bias")
    if not 1 <= int(sample_count) <= 10_000_000: raise ValueError("sample_count out of range")
    payload={"client_id":client_id,"round_id":round_id,"weights":[float(x) for x in vector],
             "bias":float(bias),"sample_count":int(sample_count)}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
    calculated=hashlib.sha256(canonical.encode()).hexdigest()
    if not hmac.compare_digest(calculated,str(update_hash)): raise ValueError("update hash mismatch")
    with connect() as c:
        client=_client_secret(c,client_id)
        if not client or client["status"]!="active": raise PermissionError("client is not active")
        # Client secret is represented by its hash at rest; HMAC verifies using the one-time
        # client secret supplied in Authorization by the agent, checked against stored hash.
        raise RuntimeError("Use submit_update_with_secret so the secret is verified without storing plaintext.")

def submit_update_with_secret(client_id, signature, round_id, weights, bias, sample_count,
                              validation_auc=0.5, validation_accuracy=0.0,
                              poisoned_row_count=0, feature_columns=None):
    import numpy as np
    vector=np.asarray(weights,dtype=float)
    if vector.ndim!=1 or vector.size<1 or vector.size>10000 or not np.isfinite(vector).all() or not math.isfinite(float(bias)):
        raise ValueError("model update must contain finite numeric weights and bias")
    if not 1 <= int(sample_count) <= 10_000_000: raise ValueError("sample_count out of range")
    if not math.isfinite(float(validation_auc)) or not 0.0 <= float(validation_auc) <= 1.0:
        raise ValueError("validation_auc must be between 0 and 1")
    if not math.isfinite(float(validation_accuracy)) or not 0.0 <= float(validation_accuracy) <= 1.0:
        raise ValueError("validation_accuracy must be between 0 and 1")
    if not 0 <= int(poisoned_row_count) <= int(sample_count):
        raise ValueError("poisoned_row_count must be between zero and sample_count")
    feature_columns=[str(name) for name in (feature_columns or [])]
    if feature_columns and (len(feature_columns)!=len(vector) or len(set(feature_columns))!=len(feature_columns)):
        raise ValueError("feature columns must be unique and match the update dimension")
    payload={"client_id":client_id,"round_id":round_id,"weights":[float(x) for x in vector],
             "bias":float(bias),"sample_count":int(sample_count)}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
    update_hash=hashlib.sha256(canonical.encode()).hexdigest()
    with connect() as c:
        client=_client_secret(c,client_id)
        if not client or client["status"]!="active": raise PermissionError("client is not active")
        if not client["secret_hash"]:
            raise PermissionError("client signing credential unavailable")
        signing_key=bytes.fromhex(client["secret_hash"])
        expected_signature=hmac.new(signing_key,canonical.encode(),hashlib.sha256).hexdigest()
        if not hmac.compare_digest(str(signature),expected_signature):
            raise PermissionError("invalid client update signature")
        round_row=c.execute("SELECT status FROM federated_rounds WHERE round_id=?",(round_id,)).fetchone()
        if not round_row or round_row["status"]!="collecting":
            raise ValueError("round does not exist or is not accepting updates")
        duplicate=c.execute("SELECT 1 FROM model_updates WHERE round_id=? AND client_id=?",(round_id,client_id)).fetchone()
        if duplicate: raise ValueError("this client has already submitted an update for the round")
        model=c.execute("SELECT weights_json,bias,version,feature_columns_json FROM global_model WHERE singleton=1").fetchone()
        global_w=json.loads(model["weights_json"])
        if global_w and len(global_w)!=len(vector): raise ValueError("update dimension does not match global model")
        global_features=json.loads(model["feature_columns_json"] or "[]")
        if global_w and global_features and feature_columns and global_features!=feature_columns:
            raise ValueError("update feature names or order do not match the global model")
        # First model establishes dimensionality; subsequent rounds require consistent dimensions.
        if global_w:
            ref=np.asarray(global_w,dtype=float)
            denom=max(float(np.linalg.norm(vector)),float(np.linalg.norm(ref)),1e-9)
            similarity=max(0.0,1.0-float(np.linalg.norm(vector-ref))/denom)
        else:
            # There is no prior coordinator model to compare against yet.
            similarity=0.5
        integrity=1.0 if hmac.compare_digest(str(signature),expected_signature) else 0.0
        validation=float(validation_auc)
        # Dataset poisoning markers are useful evidence for this local demo, while
        # the coordinator AUC is independently calculated from its labeled holdout.
        # Scores are per-round and do not inherit a bonus from prior scores.
        poisoning=1.0 if int(poisoned_row_count)>0 or validation<0.5 else max(0.0,min(1.0,(0.55-validation)/0.10))
        validation_score=max(0.0,min(1.0,(validation-0.5)/0.20))
        score=max(0.0,min(1.0,0.20*integrity+0.15*similarity+0.50*validation_score+0.15*(1-poisoning)))
        if int(poisoned_row_count)>0:
            accepted=False
            reason=f"client_reported_poison_marker:{int(poisoned_row_count)} rows"
        elif validation<0.55:
            accepted=False
            reason="trusted_validation_auc_below_threshold"
        else:
            accepted=bool(integrity and score>=0.55)
            reason="accepted" if accepted else "trust_score_below_threshold"
        update_id=uuid.uuid4().hex
        c.execute("""INSERT INTO model_updates VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
          (update_id,round_id,client_id,update_hash,int(integrity),int(accepted),score,0.0,int(sample_count),reason,time.time()))
        c.execute("""INSERT INTO client_trust(client_id,round_id,score,integrity,similarity,validation,validation_accuracy,poisoning,weight,reason,created_at)
          VALUES(?,?,?,?,?,?,?,?,?,?,?)""",(client_id,round_id,score,integrity,similarity,validation,
            float(validation_accuracy),poisoning,0.0,reason,time.time()))
        c.execute("INSERT INTO federated_update_payloads(update_id,weights_json,bias,feature_columns_json) VALUES(?,?,?,?)",
                  (update_id,json.dumps(vector.tolist()),float(bias),json.dumps(feature_columns)))
        audit(c,"model_update."+reason,client_id,{"round_id":round_id,"update_id":update_id,"hash":update_hash,"trust":score})
        return {"update_id":update_id,"round_id":round_id,"client_id":client_id,"accepted":accepted,
                "trust_score":score,"integrity":integrity,"similarity":similarity,"validation_auc":validation,
                "validation_accuracy":float(validation_accuracy),
                "validation_score":validation_score,"poisoning":poisoning,"poisoned_row_count":int(poisoned_row_count),
                "aggregation_weight":0.0,"reason":reason,"update_hash":update_hash,
                "weights":vector.tolist(),"bias":float(bias),"sample_count":int(sample_count)}

def submit_update_for_session(client_id, round_id, weights, bias, sample_count,
                              validation_auc=0.5, validation_accuracy=0.0,
                              poisoned_row_count=0, feature_columns=None):
    """Submit an update authenticated by the client's existing dashboard session."""
    import numpy as np
    vector=np.asarray(weights,dtype=float)
    if vector.ndim!=1 or vector.size<1 or vector.size>10000 or not np.isfinite(vector).all() or not math.isfinite(float(bias)):
        raise ValueError("model update must contain finite numeric weights and bias")
    if not 1 <= int(sample_count) <= 10_000_000: raise ValueError("sample_count out of range")
    payload={"client_id":client_id,"round_id":round_id,"weights":[float(x) for x in vector],
             "bias":float(bias),"sample_count":int(sample_count)}
    canonical=json.dumps(payload,sort_keys=True,separators=(",",":"))
    with connect() as c:
        client=_client_secret(c,client_id)
        if not client or client["status"]!="active": raise PermissionError("client is not active")
        signing_key=bytes.fromhex(client["secret_hash"])
        signature=hmac.new(signing_key,canonical.encode(),hashlib.sha256).hexdigest()
    return submit_update_with_secret(client_id,signature,round_id,weights,bias,sample_count,
        validation_auc=validation_auc,validation_accuracy=validation_accuracy,
        poisoned_row_count=poisoned_row_count,feature_columns=feature_columns)

def create_round():
    rid="R-"+uuid.uuid4().hex[:12].upper()
    with connect() as c:
        m=c.execute("SELECT version FROM global_model WHERE singleton=1").fetchone()
        c.execute("INSERT INTO federated_rounds(round_id,status,model_version,created_at) VALUES(?,?,?,?)",
                  (rid,"collecting",m["version"],time.time()))
        audit(c,"federated_round.created","admin",{"round_id":rid,"model_version":m["version"]})
    return {"round_id":rid,"status":"collecting","model_version":m["version"]}

def list_collecting_rounds():
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT round_id,model_version,created_at FROM federated_rounds WHERE status='collecting' ORDER BY created_at DESC")]

def aggregate_round(round_id, validator=None):
    import numpy as np
    with connect() as c:
        rows=list(c.execute("""SELECT u.*,p.weights_json,p.bias,p.feature_columns_json FROM model_updates u
          JOIN federated_update_payloads p ON p.update_id=u.update_id
          WHERE u.round_id=? AND u.accepted=1""",(round_id,)).fetchall())
        if not rows: raise ValueError("no accepted client updates for this round")
        vectors=[np.asarray(json.loads(r["weights_json"]),dtype=float) for r in rows]
        if any(v.shape!=vectors[0].shape or not np.isfinite(v).all() for v in vectors):
            raise ValueError("incompatible or invalid client model updates")
        feature_schemas=[json.loads(r["feature_columns_json"] or "[]") for r in rows]
        nonempty_schemas=[schema for schema in feature_schemas if schema]
        if nonempty_schemas and any(schema!=nonempty_schemas[0] for schema in nonempty_schemas):
            raise ValueError("client feature names or order differ within this round")
        feature_columns=nonempty_schemas[0] if nonempty_schemas else []
        # Older stored updates predate schema persistence. The dashboard's
        # supported model has this stable five-column order.
        if validator and not feature_columns and vectors[0].size==5:
            feature_columns=["voltage","current","power","consumption_kwh","power_factor"]
        model=c.execute("SELECT version,weights_json,bias,feature_columns_json FROM global_model WHERE singleton=1").fetchone()
        current_weights=np.asarray(json.loads(model["weights_json"]),dtype=float)
        current_bias=float(model["bias"])
        current_features=json.loads(model["feature_columns_json"] or "[]")
        if current_weights.size and current_features and feature_columns and current_features!=feature_columns:
            raise ValueError("client feature names or order differ from the current global model")
        if validator and not feature_columns:
            raise ValueError("model feature schema is unavailable for coordinator validation")

        def build_aggregate(indices):
            sub_vectors=[vectors[i] for i in indices]
            sub_rows=[rows[i] for i in indices]
            peers_for_client=[]
            for i,vec in zip(indices,sub_vectors):
                peers=[vectors[j] for j in indices if j!=i]
                if not peers:
                    peers_for_client.append(0.5)
                    continue
                peer_reference=np.median(np.stack(peers),axis=0)
                denom=max(float(np.linalg.norm(vec)),float(np.linalg.norm(peer_reference)),1e-9)
                peers_for_client.append(max(0.0,min(1.0,1.0-float(np.linalg.norm(vec-peer_reference))/denom)))
            scores=[max(0.0,min(1.0,0.75*float(row["trust_score"])+0.25*peer))
                    for row,peer in zip(sub_rows,peers_for_client)]
            raw=np.asarray([score*int(row["sample_count"]) for row,score in zip(sub_rows,scores)],dtype=float)
            if raw.sum()<=0:
                raise ValueError("all accepted client aggregation weights are zero")
            normalized=raw/raw.sum()
            aggregate_weights=np.average(np.stack(sub_vectors),axis=0,weights=normalized)
            aggregate_bias=float(np.average(np.asarray([row["bias"] for row in sub_rows],dtype=float),weights=normalized))
            return aggregate_weights,aggregate_bias,normalized,peers_for_client

        baseline_metrics=None
        if validator:
            if current_weights.size:
                baseline_metrics=validator(feature_columns,current_weights.tolist(),current_bias)
            else:
                # Use the majority class as the no-model baseline, rather than
                # interpreting zero logits as a positive-class prediction.
                baseline_metrics=validator(feature_columns,np.zeros(len(feature_columns)).tolist(),-1e-9)
        active=list(range(len(rows)))
        removed=[]
        global_weights,global_bias,normalized,peer_scores=build_aggregate(active)
        candidate_metrics=validator(feature_columns,global_weights.tolist(),global_bias) if validator else None

        def regresses(metrics):
            if not validator or not baseline_metrics or not metrics:
                return False
            return (float(metrics["accuracy"]) < float(baseline_metrics["accuracy"])-0.005
                    or float(metrics["auc"]) < float(baseline_metrics["auc"])-0.01)

        # Greedily remove the update whose exclusion most improves the aggregate.
        # The coordinator never installs a model that degrades its labeled reference.
        while regresses(candidate_metrics) and active:
            best_index=None
            best_gain=0.0
            for index in active:
                remaining=[i for i in active if i!=index]
                if remaining:
                    test_weights,test_bias,_,_=build_aggregate(remaining)
                    metrics=validator(feature_columns,test_weights.tolist(),test_bias)
                else:
                    metrics=baseline_metrics
                gain=((float(metrics["accuracy"])-float(candidate_metrics["accuracy"]))
                      +(float(metrics["auc"])-float(candidate_metrics["auc"])))
                if gain>best_gain:
                    best_gain=gain
                    best_index=index
            if best_index is None:
                # If interactions prevent a unique attribution, reject all of the
                # updates in the degrading aggregate rather than guessing a culprit.
                removed.extend(active)
                active=[]
                break
            removed.append(best_index)
            active.remove(best_index)
            if active:
                global_weights,global_bias,normalized,peer_scores=build_aggregate(active)
                candidate_metrics=validator(feature_columns,global_weights.tolist(),global_bias) if validator else None
            else:
                candidate_metrics=baseline_metrics

        reason="coordinator_model_quality_regression"
        for index in removed:
            row=rows[index]
            lowered=max(0.0,float(row["trust_score"])-0.25)
            c.execute("UPDATE model_updates SET accepted=0,trust_score=?,reason=? WHERE update_id=?",
                      (lowered,reason,row["update_id"]))
            c.execute("UPDATE client_trust SET score=?,poisoning=1.0,weight=0.0,reason=? WHERE client_id=? AND round_id=?",
                      (lowered,reason,row["client_id"],round_id))
            audit(c,"model_update.coordinator_quality_rejected",row["client_id"],
                  {"round_id":round_id,"update_id":row["update_id"],"trust":lowered,
                   "reference_accuracy":candidate_metrics.get("accuracy") if candidate_metrics else None,
                   "reference_auc":candidate_metrics.get("auc") if candidate_metrics else None})
        if not active:
            total=int(c.execute("SELECT COUNT(*) n FROM model_updates WHERE round_id=?",(round_id,)).fetchone()["n"])
            c.execute("UPDATE federated_rounds SET status='quality_rejected',participants=?,accepted=0,rejected=?,completed_at=? WHERE round_id=?",
                      (total,total,time.time(),round_id))
            audit(c,"federated_round.quality_rejected","coordinator",{"round_id":round_id,
                "accuracy":candidate_metrics.get("accuracy") if candidate_metrics else None,
                "auc":candidate_metrics.get("auc") if candidate_metrics else None})
            return {"round_id":round_id,"status":"quality_rejected","model_version":int(model["version"]),
                    "participants":total,"accepted":0,"rejected":total,
                    "reason":"aggregation would lower coordinator reference performance; global model unchanged",
                    "validation":candidate_metrics}
        rows=[rows[i] for i in active]
        vectors=[vectors[i] for i in active]
        for row,peer_score in zip(rows,peer_scores):
            c.execute("UPDATE client_trust SET similarity=? WHERE client_id=? AND round_id=?",
                      (peer_score,row["client_id"],round_id))
        privacy_report={"enabled":False,"reason":"TRUSTFED_DP_ENABLED is not enabled"}
        if os.getenv("TRUSTFED_DP_ENABLED","0").lower() in {"1","true","yes"}:
            from src.security.privacy_accountant import GaussianRDPAccountant
            clip_norm=float(os.getenv("TRUSTFED_DP_CLIP_NORM","5.0"))
            noise_multiplier=float(os.getenv("TRUSTFED_DP_NOISE_MULTIPLIER","1.5"))
            delta=float(os.getenv("TRUSTFED_DP_DELTA","1e-5"))
            max_epsilon=float(os.getenv("TRUSTFED_DP_MAX_EPSILON","10.0"))
            if not all(math.isfinite(v) and v>0 for v in (clip_norm,noise_multiplier,max_epsilon)) or not 0<delta<1:
                raise ValueError("invalid differential privacy configuration")
            accountant=GaussianRDPAccountant()
            previous=c.execute("SELECT orders_json,rdp_json,rounds FROM privacy_accounting WHERE singleton=1").fetchone()
            if previous is not None:
                accountant.orders=__import__("numpy").asarray(json.loads(previous["orders_json"]),dtype=float)
                accountant.rdp=__import__("numpy").asarray(json.loads(previous["rdp_json"]),dtype=float)
                accountant.steps=int(previous["rounds"])
            accountant.step(noise_multiplier)
            epsilon=accountant.epsilon(delta)
            if epsilon>max_epsilon:
                raise ValueError(f"privacy budget exhausted: projected epsilon {epsilon:.4f} exceeds {max_epsilon:.4f}")
            # Clip each complete (weights,bias) vector before weighted aggregation.
            import numpy as np
            clipped=[]
            for vec,row in zip(vectors,rows):
                complete=np.r_[vec,float(row["bias"])]
                norm=float(np.linalg.norm(complete))
                clipped.append(complete*min(1.0,clip_norm/max(norm,1e-12)))
            aggregate=np.average(np.stack(clipped),axis=0,weights=normalized)
            sensitivity=2.0*clip_norm*float(np.max(normalized))
            sigma=noise_multiplier*sensitivity
            rng=np.random.default_rng()
            aggregate=aggregate+rng.normal(0.0,sigma,size=aggregate.shape)
            global_weights=aggregate[:-1]
            global_bias=float(aggregate[-1])
            c.execute("""INSERT INTO privacy_accounting(singleton,orders_json,rdp_json,rounds,epsilon,delta,updated_at)
              VALUES(1,?,?,?,?,?,?) ON CONFLICT(singleton) DO UPDATE SET orders_json=excluded.orders_json,
              rdp_json=excluded.rdp_json,rounds=excluded.rounds,epsilon=excluded.epsilon,delta=excluded.delta,updated_at=excluded.updated_at""",
              (json.dumps(accountant.orders.tolist()),json.dumps(accountant.rdp.tolist()),accountant.steps,epsilon,delta,time.time()))
            privacy_report={"enabled":True,"mechanism":"per-client L2 clipping + Gaussian noise on weighted aggregate",
              "accounting":"full-participation Gaussian RDP; no subsampling amplification",
              "rounds_accounted":accountant.steps,"epsilon":epsilon,"delta":delta,
              "clip_norm":clip_norm,"noise_multiplier":noise_multiplier}
        if validator:
            candidate_metrics=validator(feature_columns,global_weights.tolist(),global_bias)
            if regresses(candidate_metrics):
                reason="coordinator_model_quality_regression"
                for row in rows:
                    lowered=max(0.0,float(row["trust_score"])-0.25)
                    c.execute("UPDATE model_updates SET accepted=0,trust_score=?,reason=? WHERE update_id=?",
                              (lowered,reason,row["update_id"]))
                    c.execute("UPDATE client_trust SET score=?,poisoning=1.0,weight=0.0,reason=? WHERE client_id=? AND round_id=?",
                              (lowered,reason,row["client_id"],round_id))
                    audit(c,"model_update.coordinator_quality_rejected",row["client_id"],
                          {"round_id":round_id,"update_id":row["update_id"],"trust":lowered,
                           "reference_accuracy":candidate_metrics.get("accuracy"),
                           "reference_auc":candidate_metrics.get("auc")})
                total=int(c.execute("SELECT COUNT(*) n FROM model_updates WHERE round_id=?",(round_id,)).fetchone()["n"])
                c.execute("UPDATE federated_rounds SET status='quality_rejected',participants=?,accepted=0,rejected=?,completed_at=? WHERE round_id=?",
                          (total,total,time.time(),round_id))
                audit(c,"federated_round.quality_rejected","coordinator",{"round_id":round_id,
                    "accuracy":candidate_metrics.get("accuracy"),"auc":candidate_metrics.get("auc"),
                    "reason":"differential privacy noise lowered reference performance"})
                return {"round_id":round_id,"status":"quality_rejected","model_version":int(model["version"]),
                        "participants":total,"accepted":0,"rejected":total,
                        "reason":"noisy aggregate lowered coordinator reference performance; global model unchanged",
                        "validation":candidate_metrics,"privacy":privacy_report}
        current=int(model["version"])
        new_version=int(current)+1
        c.execute("UPDATE global_model SET version=?,weights_json=?,bias=?,updated_at=?,feature_columns_json=? WHERE singleton=1",
                  (new_version,json.dumps(global_weights.tolist()),global_bias,time.time(),json.dumps(feature_columns)))
        for r,w in zip(rows,normalized):
            c.execute("UPDATE model_updates SET aggregation_weight=? WHERE update_id=?",(float(w),r["update_id"]))
            c.execute("UPDATE client_trust SET weight=? WHERE client_id=? AND round_id=?",
                      (float(w),r["client_id"],round_id))
        total=c.execute("SELECT COUNT(*) n FROM model_updates WHERE round_id=?",(round_id,)).fetchone()["n"]
        rejected=int(total)-len(rows)
        c.execute("UPDATE federated_rounds SET status='completed',participants=?,accepted=?,rejected=?,completed_at=? WHERE round_id=?",
                  (int(total),len(rows),rejected,time.time(),round_id))
        audit(c,"federated_round.aggregated","coordinator",{"round_id":round_id,"model_version":new_version,
             "accepted":len(rows),"rejected":rejected,"validation":candidate_metrics,
             "weights":{r["client_id"]:float(w) for r,w in zip(rows,normalized)}})
        return {"round_id":round_id,"status":"completed","model_version":new_version,
                "participants":int(total),"accepted":len(rows),"rejected":rejected,
                "client_weights":{r["client_id"]:float(w) for r,w in zip(rows,normalized)},
                "trust_scores":{r["client_id"]:float(r["trust_score"]) for r in rows},
                "global_model":{"version":new_version,"weights":global_weights.tolist(),"bias":global_bias,
                                "feature_columns":feature_columns},
                "validation":candidate_metrics,
                "privacy":privacy_report}



def register_dataset(client_id, filename, sha256, row_count, feature_columns, label_column):
    if not filename or len(filename)>255 or len(sha256)!=64 or any(ch not in "0123456789abcdef" for ch in sha256.lower()):
        raise ValueError("invalid dataset filename or SHA-256 digest")
    if not 1 <= int(row_count) <= 100_000_000: raise ValueError("row_count out of range")
    if not feature_columns or len(feature_columns)>500: raise ValueError("feature_columns required")
    dataset_id="DS-"+uuid.uuid4().hex[:12].upper()
    with connect() as c:
        c.execute("""INSERT INTO client_datasets VALUES(?,?,?,?,?,?,?,?)""",
          (dataset_id,client_id,Path(filename).name,sha256.lower(),int(row_count),
           json.dumps(feature_columns),label_column,time.time()))
        audit(c,"dataset.metadata_registered",client_id,{"dataset_id":dataset_id,"sha256":sha256.lower(),"row_count":int(row_count)})
    return {"dataset_id":dataset_id,"filename":Path(filename).name,"sha256":sha256.lower(),
            "row_count":int(row_count),"feature_columns":feature_columns,"label_column":label_column}

def list_datasets(client_id):
    with connect() as c:
        rows=c.execute("SELECT * FROM client_datasets WHERE client_id=? ORDER BY created_at DESC",(client_id,)).fetchall()
        return [{**dict(r),"feature_columns":json.loads(r["feature_columns_json"])} for r in rows]

def list_client_updates(client_id):
    with connect() as c:
        return [dict(r) for r in c.execute("""SELECT update_id,round_id,update_hash,signature_valid,accepted,
          trust_score,aggregation_weight,sample_count,reason,created_at FROM model_updates
          WHERE client_id=? ORDER BY created_at DESC LIMIT 100""",(client_id,))]

def list_trust(client_id=None):
    with connect() as c:
        if client_id:
            rows=c.execute("SELECT * FROM client_trust WHERE client_id=? ORDER BY id DESC LIMIT 100",(client_id,)).fetchall()
        else:
            rows=c.execute("SELECT * FROM client_trust ORDER BY id DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]

def list_audit(limit=100):
    with connect() as c:
        rows=c.execute("SELECT * FROM audit_events ORDER BY id DESC LIMIT ?",(limit,)).fetchall()
        return [dict(r) for r in rows]

def verify_audit_chain():
    rows=list(reversed(list_audit(100000)))
    previous="0"*64
    for r in rows:
        body=json.dumps(json.loads(r["payload_json"]),sort_keys=True,separators=(",",":"),default=str)
        expected=hashlib.sha256(f"{previous}|{r['event_type']}|{r['actor_id']}|{r['created_at']:.6f}|{body}".encode()).hexdigest()
        if not hmac.compare_digest(expected,r["event_hash"]): return {"valid":False,"failed_event_id":r["id"]}
        previous=r["event_hash"]
    return {"valid":True,"events_checked":len(rows)}
