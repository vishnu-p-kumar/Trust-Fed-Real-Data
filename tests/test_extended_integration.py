import numpy as np
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from src.federated.model_distillation import federated_teacher_targets, distill_global_student
from src.security.totp import code, verify
from src.jobs.sqlite_queue import SQLiteJobQueue
from src.investigation.case_manager import CaseManager

def test_model_family_distillation_from_tree_teachers():
    X=np.r_[np.random.default_rng(1).normal(-1,.3,(40,3)),np.random.default_rng(2).normal(1,.3,(40,3))]
    y=np.r_[np.zeros(40,dtype=int),np.ones(40,dtype=int)]
    a=RandomForestClassifier(n_estimators=8,random_state=1).fit(X,y)
    b=RandomForestClassifier(n_estimators=8,random_state=2).fit(X,y)
    teacher,_=federated_teacher_targets([a,b],X,client_weights=[1,2])
    student,meta=distill_global_student(X,teacher)
    assert student.coef_.shape==(1,3) and meta["anchor_rows"]==80

def test_totp_rfc6238_window():
    secret="GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    token=code(secret,59,period=30,digits=8)
    assert token=="94287082"
    assert verify(secret,token,timestamp=59,window=0)

def test_sqlite_queue_claim_and_finish(tmp_path):
    q=SQLiteJobQueue(tmp_path/"q.db"); job=q.enqueue("test",{"x":1})
    claimed=q.claim(); assert claimed["id"]==job["id"]
    finished=q.finish(job["id"],{"ok":True}); assert finished["status"]=="completed"
