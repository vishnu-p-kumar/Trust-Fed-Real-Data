"""External benchmark on TDD2022, using unseen consumer classes as held-out groups.

Important: TDD2022 applies six synthetic theft transformations to OEDI profiles.
It is an independent data source but NOT independently verified real theft.
Results must be reported separately from the SGCC real-label benchmark.
"""
from __future__ import annotations
import argparse,json
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.ensemble import ExtraTreesClassifier,HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import average_precision_score,roc_auc_score,precision_recall_curve,precision_score,recall_score,f1_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.utils.class_weight import compute_sample_weight

ROOT=Path(__file__).resolve().parents[1]

def _label(s):
    z=s.astype(str).str.strip().str.lower()
    mapped=z.map({'normal':0,'0':0,'false':0,'no_theft':0,'non-theft':0})
    return mapped.fillna((z!='normal').astype(int)).astype(int)

def _threshold(y,p,target):
    pr,re,ts=precision_recall_curve(y,p);pr,re=pr[:-1],re[:-1]
    f=2*pr*re/np.maximum(pr+re,1e-12);idx=np.flatnonzero(re>=target)
    if not len(idx):return .5
    return float(ts[idx[np.argmax(f[idx])]])

def _split(X,y,g,seed,test_size):
    splitter=GroupShuffleSplit(n_splits=100,test_size=test_size,random_state=seed)
    for tr,te in splitter.split(X,y,g):
        if len(np.unique(y[tr]))==2 and len(np.unique(y[te]))==2 and len(set(g[tr])&set(g[te]))==0:
            return tr,te
    raise ValueError('Could not create a two-class holdout by unseen consumer Class; check data/schema and class coverage.')

def evaluate(frame,seeds=(11,23,37),target_recall=.4):
    normalized={str(c).strip().lower():c for c in frame.columns}
    label_col=normalized.get('theft') or normalized.get('theft_type') or normalized.get('theft_label')
    group_col=normalized.get('class') or normalized.get('consumer_class')
    if label_col is None or group_col is None:raise ValueError('TDD2022 file must contain Theft and Class columns')
    if frame[label_col].isna().any() or frame[group_col].isna().any():raise ValueError('Theft and Class columns cannot contain missing values')
    y=_label(frame[label_col]).to_numpy();g=frame[group_col].astype(str).to_numpy()
    excluded=[c for c in frame.columns if str(c).strip().lower() in {str(label_col).strip().lower(),str(group_col).strip().lower(),'theft_binary','is_theft','theft_type','label','target','id','meter_id','customer_id'}]
    X=frame.drop(columns=excluded).select_dtypes(include=[np.number,'bool']).replace([np.inf,-np.inf],np.nan)
    if X.empty or len(np.unique(y))!=2:raise ValueError('need numeric meter channels and both binary labels')
    records=[]
    for seed in seeds:
        train,test=_split(X,y,g,seed,.20)
        fit,val=_split(X.iloc[train],y[train],g[train],seed+1000,.20)
        fit_idx=train[fit];val_idx=train[val]
        models={
          'extra_trees':ExtraTreesClassifier(n_estimators=100,min_samples_leaf=2,max_features=.8,class_weight='balanced',n_jobs=1,random_state=seed),
          'hist_gradient_boosting':HistGradientBoostingClassifier(max_iter=120,learning_rate=.08,max_leaf_nodes=15,l2_regularization=2,random_state=seed)}
        candidates=[]
        for name,model in models.items():
            pipe=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),model)
            if name=='hist_gradient_boosting':pipe.fit(X.iloc[fit_idx],y[fit_idx],histgradientboostingclassifier__sample_weight=compute_sample_weight('balanced',y[fit_idx]))
            else:pipe.fit(X.iloc[fit_idx],y[fit_idx])
            pv=pipe.predict_proba(X.iloc[val_idx])[:,1]
            candidates.append((average_precision_score(y[val_idx],pv),name,model,pv))
        _,name,model,pv=max(candidates,key=lambda z:z[0]);threshold=_threshold(y[val_idx],pv,target_recall)
        final=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),model)
        if name=='hist_gradient_boosting':final.fit(X.iloc[train],y[train],histgradientboostingclassifier__sample_weight=compute_sample_weight('balanced',y[train]))
        else:final.fit(X.iloc[train],y[train])
        pt=final.predict_proba(X.iloc[test])[:,1];pred=pt>=threshold
        records.append({'seed':int(seed),'selected_model':name,'train_classes':sorted(set(g[train])),'test_classes':sorted(set(g[test])),
          'class_overlap':len(set(g[train])&set(g[test])),'test_pr_auc':float(average_precision_score(y[test],pt)),
          'test_roc_auc':float(roc_auc_score(y[test],pt)),'test_precision':float(precision_score(y[test],pred,zero_division=0)),
          'test_recall':float(recall_score(y[test],pred,zero_division=0)),'test_f1':float(f1_score(y[test],pred,zero_division=0)),
          'threshold':float(threshold),'test_rows':int(len(test))})
    return {'dataset':'TDD2022/OEDI-derived benchmark','label_provenance':'Six synthetic theft transformations applied to measured OEDI consumption profiles; not field-verified theft.',
      'protocol':'Group holdout by consumer Class: test classes are unseen during fitting; inner group validation selects model and recall-constrained threshold.',
      'target_recall':target_recall,'records':records,'limitations':['This is synthetic attack-label evaluation, not verified utility theft ground truth.',
      'The consumer Class holdout tests unseen building types, not unseen individual meter identities.',
      'Do not pool these metrics with SGCC metrics; data distributions and label provenance differ.']}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,default=ROOT/'datasets/tdd2022/raw/df.csv')
    p.add_argument('--seeds',default='11,23,37');p.add_argument('--target-recall',type=float,default=.4)
    p.add_argument('--output',type=Path,default=ROOT/'reports/research_runs/tdd2022_external_benchmark.json');a=p.parse_args()
    if not 0<a.target_recall<=1:raise ValueError('--target-recall must be in (0,1]')
    seeds=[int(v) for v in a.seeds.split(',') if v.strip()]
    if len(seeds)<3 or len(set(seeds))!=len(seeds):raise ValueError('provide at least three unique seeds')
    if not a.input.is_file():raise FileNotFoundError(f'{a.input} not found. Run: python scripts/download_tdd2022.py')
    result=evaluate(pd.read_csv(a.input,low_memory=False),seeds,a.target_recall)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2,allow_nan=False));print(json.dumps({'output':str(a.output),'runs':len(result['records'])},indent=2))
if __name__=='__main__':main()
