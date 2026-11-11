"""Full-cohort PR-AUC-oriented SGCC model selection with recall-constrained thresholding.

Uses customer-disjoint outer test and inner validation splits. Model family is
selected on validation Average Precision (PR-AUC); threshold is selected on
validation only to maximise F1 subject to a minimum recall. The test set is
never used for model/threshold selection.
"""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score,
    confusion_matrix, f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score, precision_recall_curve)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.utils.class_weight import compute_sample_weight

ROOT=Path(__file__).resolve().parents[1]

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()

def models(seed):
    return {
      'extra_trees_balanced': ExtraTreesClassifier(n_estimators=120,min_samples_leaf=3,
        max_features=.7,class_weight='balanced',n_jobs=1,random_state=seed),
      'hist_gradient_boosting_balanced': HistGradientBoostingClassifier(max_iter=120,
        learning_rate=.08,max_leaf_nodes=15,l2_regularization=2.0,random_state=seed),
    }

def metric(y,p,t):
    pred=(p>=t).astype('int8'); tn,fp,fn,tp=confusion_matrix(y,pred,labels=[0,1]).ravel()
    return {'accuracy':float(accuracy_score(y,pred)),'precision':float(precision_score(y,pred,zero_division=0)),
      'recall':float(recall_score(y,pred,zero_division=0)),'f1':float(f1_score(y,pred,zero_division=0)),
      'balanced_accuracy':float(balanced_accuracy_score(y,pred)),'roc_auc':float(roc_auc_score(y,p)),
      'pr_auc':float(average_precision_score(y,p)),'false_positive_rate':float(fp/max(1,fp+tn)),
      'mcc':float(matthews_corrcoef(y,pred)),'threshold':float(t),
      'confusion_matrix':{'tn':int(tn),'fp':int(fp),'fn':int(fn),'tp':int(tp)}}

def threshold_for_recall(y,p,target):
    precision,recall,thresholds=precision_recall_curve(y,p)
    # precision/recall have one extra endpoint; thresholds align with all but the last.
    precision,recall=precision[:-1],recall[:-1]
    f1=2*precision*recall/np.maximum(precision+recall,1e-12)
    feasible=np.flatnonzero(recall>=target)
    if not len(feasible):
        raise ValueError(f'validation recall target {target:.3f} is infeasible')
    best=feasible[np.argmax(f1[feasible])]
    return float(thresholds[best]), {'f1':float(f1[best]),'precision':float(precision[best]),'recall':float(recall[best])}

def fit_predict(name,model,xfit,yfit,xout,seed):
    pipe=make_pipeline(SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True),model)
    if name=='hist_gradient_boosting_balanced':
        pipe.fit(xfit,yfit,histgradientboostingclassifier__sample_weight=compute_sample_weight('balanced',yfit))
    else: pipe.fit(xfit,yfit)
    return pipe.predict_proba(xout)[:,1],pipe

def evaluate(frame,seeds,target_recall):
    required={'meter_id','is_theft'}
    if not required.issubset(frame.columns): raise ValueError(f'missing columns: {sorted(required-set(frame.columns))}')
    if frame.meter_id.isna().any() or frame.meter_id.astype(str).duplicated().any():
        raise ValueError('meter_id must be non-null and unique: one row per customer is required')
    y=frame.is_theft.astype(int).to_numpy()
    if set(np.unique(y))!={0,1}: raise ValueError('both binary classes are required')
    X=frame.drop(columns=['meter_id','is_theft']).select_dtypes(include=[np.number,'bool']).replace([np.inf,-np.inf],np.nan)
    if X.empty: raise ValueError('no numeric features found')
    groups=frame.meter_id.astype(str).to_numpy(); rows=[]
    for seed in seeds:
        outer=GroupShuffleSplit(n_splits=1,test_size=.20,random_state=seed)
        train_idx,test_idx=next(outer.split(X,y,groups))
        inner=GroupShuffleSplit(n_splits=1,test_size=.20,random_state=seed+1000)
        fit_rel,val_rel=next(inner.split(X.iloc[train_idx],y[train_idx],groups[train_idx]))
        fit_idx,val_idx=train_idx[fit_rel],train_idx[val_rel]
        candidates=[]
        for name,model in models(seed).items():
            val_prob,_=fit_predict(name,model,X.iloc[fit_idx],y[fit_idx],X.iloc[val_idx],seed)
            candidates.append({'name':name,'model':model,'val_prob':val_prob,'val_pr_auc':float(average_precision_score(y[val_idx],val_prob)),
              'val_recall_at_05':float(recall_score(y[val_idx],val_prob>=.5))})
        selected=max(candidates,key=lambda r:r['val_pr_auc'])
        # Threshold calibration on validation only, with a recall floor.
        val_prob=selected['val_prob']
        threshold,val_operating=threshold_for_recall(y[val_idx],val_prob,target_recall)
        test_prob,final_model=fit_predict(selected['name'],selected['model'],X.iloc[train_idx],y[train_idx],X.iloc[test_idx],seed)
        rows.append({'seed':int(seed),'selected_model':selected['name'],'validation_candidates':[
          {k:v for k,v in c.items() if k not in {'model','val_prob'}} for c in candidates],
          'validation_selected_pr_auc':selected['val_pr_auc'],'validation_recall_target':target_recall,
          'selected_threshold':threshold,'validation_operating_point':val_operating,
          'train_customers':int(len(train_idx)),'test_customers':int(len(test_idx)),
          'customer_overlap':int(len(set(groups[train_idx])&set(groups[test_idx]))),
          'test_fixed_05':metric(y[test_idx],test_prob,.5),
          'test_recall_constrained':metric(y[test_idx],test_prob,threshold)})
    summary={}
    for mode in ('test_fixed_05','test_recall_constrained'):
        summary[mode]={}
        for key in ('accuracy','precision','recall','f1','balanced_accuracy','roc_auc','pr_auc','false_positive_rate','mcc'):
            values=np.array([r[mode][key] for r in rows],float); n=len(values)
            crit={2:4.303,3:3.182,4:2.776,5:2.571,6:2.447,7:2.365,8:2.306,9:2.262}.get(n-1,1.96)
            half=crit*values.std(ddof=1)/math.sqrt(n) if n>1 else 0
            bounds=(-1,1) if key=='mcc' else (0,1)
            summary[mode][key]={'mean':float(values.mean()),'std':float(values.std(ddof=1)) if n>1 else 0,
              'ci95_t':[float(max(bounds[0],values.mean()-half)),float(min(bounds[1],values.mean()+half))],'n':n}
    return {'dataset':'SGCC full 42,372-customer prepared benchmark','protocol':'5-seed customer-disjoint outer 80/20 holdout; inner customer-disjoint fit/validation; model selected by validation Average Precision; threshold selected on validation to maximise F1 subject to recall floor; test untouched',
      'customer_count':len(frame),'feature_count':X.shape[1],'seeds':list(seeds),'target_recall':target_recall,
      'records':rows,'summary':summary,'limitations':['SGCC is historical Chinese utility benchmark data, not Indian field validation.',
      'SGCC labels are benchmark labels; uploaded data do not include individual inspection records.',
      'Threshold selection can preserve a recall operating point but cannot increase PR-AUC; PR-AUC changes only with model ranking.',
      'TDD2022 has synthetic theft injections and CEEW has no theft ground truth; neither should be described as independently verified theft labels.']}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=ROOT/'datasets/sgcc/processed/sgcc_meter_features.csv.gz')
    p.add_argument('--seeds',default='11,23,37,53,71')
    p.add_argument('--target-recall',type=float,default=.40)
    p.add_argument('--output',type=Path,default=ROOT/'reports/research_runs/sgcc_pr_auc_optimisation.json')
    a=p.parse_args()
    if not 0<a.target_recall<=1: p.error('--target-recall must be in (0,1]')
    seeds=[int(v) for v in a.seeds.split(',') if v.strip()]
    if len(seeds)<3 or len(set(seeds))!=len(seeds): p.error('provide at least three unique seeds')
    frame=pd.read_csv(a.input,low_memory=False); result=evaluate(frame,seeds,a.target_recall)
    result['input_sha256']=sha256(a.input); a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'output':str(a.output),'summary':result['summary']},indent=2))
if __name__=='__main__': main()
