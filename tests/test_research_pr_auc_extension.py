import numpy as np
import pandas as pd
from scripts.optimize_sgcc_pr_auc import evaluate, threshold_for_recall
from scripts.evaluate_ceew_domain_shift import _psi, _features


def test_threshold_for_recall_meets_validation_recall_floor():
    y=np.array([0,0,0,0,1,1,1,1])
    p=np.array([.05,.1,.2,.35,.3,.55,.7,.9])
    threshold,details=threshold_for_recall(y,p,.75)
    assert threshold>=0
    assert details['recall']>=.75


def test_ceew_shift_psi_is_nonnegative_or_none():
    ref=np.arange(100,dtype=float)
    shifted=ref+20
    value=_psi(ref,shifted)
    assert value is None or value>=0


def test_ceew_daily_feature_builder_uses_meter_profiles():
    rows=[]
    for meter in ['M1','M2']:
        for day in pd.date_range('2021-01-01',periods=40):
            rows.append({'meter_id':meter,'date':day,'daily_kwh':float(day.day)})
    result=_features(pd.DataFrame(rows))
    assert len(result)==2
    assert {'mean_kwh','zero_rate','coefficient_variation'}.issubset(result.columns)


def test_sgcc_pr_auc_evaluation_keeps_customer_groups_disjoint():
    rng=np.random.default_rng(7)
    n=240
    y=np.array([0]*192+[1]*48)
    rng.shuffle(y)
    x1=y+rng.normal(0,.7,n)
    x2=rng.normal(size=n)
    frame=pd.DataFrame({'meter_id':[f'M{i}' for i in range(n)],'is_theft':y,'signal':x1,'noise':x2})
    result=evaluate(frame,[11,23,37],.30)
    assert all(r['customer_overlap']==0 for r in result['records'])
    assert result['summary']['test_recall_constrained']['pr_auc']['n']==3


def test_tdd2022_label_adapter_and_unseen_class_evaluation():
    from scripts.evaluate_tdd2022_external import evaluate
    rng=np.random.default_rng(42)
    rows=[]
    for cls in [f'C{i}' for i in range(12)]:
        for i in range(80):
            theft=(i%3==0)
            rows.append({'Class':cls,'Theft':'Theft1' if theft else 'Normal',
                         'Electricity:Facility':float(theft)+rng.normal(0,.3),
                         'InteriorLights:Electricity':rng.normal()})
    result=evaluate(pd.DataFrame(rows),[11,23,37],.30)
    assert all(r['class_overlap']==0 for r in result['records'])
    assert 'synthetic' in result['label_provenance'].lower()
