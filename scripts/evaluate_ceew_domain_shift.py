"""Unlabelled cross-utility shift audit: SGCC vs CEEW Mathura and Bareilly.

CEEW source tables are daily meter consumption aggregates. They have no theft
ground-truth labels, so this script reports feature-distribution shift only;
it does not calculate supervised detection metrics or PR-AUC.
"""
from __future__ import annotations
import argparse,json,re
from pathlib import Path
import numpy as np,pandas as pd
from scipy.stats import wasserstein_distance

FEATURES=['mean_kwh','std_kwh','median_kwh','min_kwh','max_kwh','p10_kwh','p25_kwh','p75_kwh','p90_kwh','zero_rate','coefficient_variation','interquartile_range_kwh']

def _features(daily):
    rows=[]
    for meter,g in daily.groupby('meter_id'):
        x=pd.to_numeric(g.sort_values('date')['daily_kwh'],errors='coerce').to_numpy(float)
        x=x[np.isfinite(x)]
        if len(x)<30: continue
        mean=float(np.mean(x)); std=float(np.std(x))
        rows.append({'meter_id':str(meter),'mean_kwh':mean,'std_kwh':std,'median_kwh':float(np.median(x)),
          'min_kwh':float(np.min(x)),'max_kwh':float(np.max(x)),'p10_kwh':float(np.quantile(x,.1)),
          'p25_kwh':float(np.quantile(x,.25)),'p75_kwh':float(np.quantile(x,.75)),
          'p90_kwh':float(np.quantile(x,.9)),'zero_rate':float(np.mean(x==0)),
          'coefficient_variation':float(std/max(abs(mean),1e-6)),
          'interquartile_range_kwh':float(np.quantile(x,.75)-np.quantile(x,.25))})
    return pd.DataFrame(rows)

def _psi(ref,cur,bins=10):
    edges=np.unique(np.quantile(ref,np.linspace(0,1,bins+1)))
    if len(edges)<3:return None
    edges[0]-=1e-12;edges[-1]+=1e-12
    a=np.histogram(ref,bins=edges)[0].astype(float);b=np.histogram(cur,bins=edges)[0].astype(float)
    a=np.maximum(a/a.sum(),1e-6);b=np.maximum(b/b.sum(),1e-6)
    return float(np.sum((b-a)*np.log(b/a)))

def _read_daily(path):
    raw=pd.read_csv(path,low_memory=False)
    norm={re.sub(r'[^a-z0-9]','',str(c).lower()):c for c in raw.columns}
    meter=next((norm[k] for k in ('meter','meterid','meter_id') if k in norm),None)
    date=next((norm[k] for k in ('date','timestamp','datetime') if k in norm),None)
    energy=next((norm[k] for k in ('tkwh','consumptionkwh','consumption','kwh') if k in norm),None)
    if not all((meter,date,energy)):raise ValueError(f'{path} needs meter, date and kWh columns; found {list(raw.columns)}')
    out=pd.DataFrame({'meter_id':raw[meter].astype(str),'date':pd.to_datetime(raw[date],errors='coerce'),
      'daily_kwh':pd.to_numeric(raw[energy],errors='coerce')}).dropna()
    return out

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sgcc',type=Path,default=Path('datasets/sgcc/processed/sgcc_meter_features.csv.gz'))
    p.add_argument('--ceew',nargs='+',type=Path,default=[Path('datasets/ceew/raw/SM Cleaned Data MH Aggregated.csv'),Path('datasets/ceew/raw/SM Cleaned Data BR Aggregated.csv')])
    p.add_argument('--output',type=Path,default=Path('reports/research_runs/ceew_cross_utility_shift.json'))
    a=p.parse_args()
    sgcc=pd.read_csv(a.sgcc,usecols=lambda c:c in set(['meter_id']+FEATURES))
    report={'comparison':'SGCC historical Chinese benchmark vs CEEW Mathura and Bareilly daily meter profiles',
      'sgcc_customers':int(len(sgcc)),'label_status':'CEEW supplied files contain no verified theft labels; supervised metrics and PR-AUC are not calculated.',
      'utilities':{},'limitations':['CEEW daily aggregates are unlabelled and cannot support theft-detection PR-AUC or recall.',
      'The CEEW cohorts are much smaller than SGCC and differ in geography, period and source construction.',
      'This is a descriptive domain-shift audit, not external supervised validation or evidence of transfer accuracy.',
      'The SGCC label provenance is inherited from the published benchmark; the supplied files do not include inspection records.']}
    for path in a.ceew:
        daily=_read_daily(path); cf=_features(daily)
        if cf.empty:raise ValueError(f'no CEEW meters with >=30 daily observations in {path}')
        loc='Bareilly' if 'br' in path.name.lower() or 'bareilly' in path.name.lower() else ('Mathura' if 'mh' in path.name.lower() or 'mathura' in path.name.lower() else path.stem)
        stats={}
        for f in FEATURES:
            if f not in sgcc or f not in cf:continue
            x=pd.to_numeric(sgcc[f],errors='coerce').dropna().to_numpy(float)
            y=pd.to_numeric(cf[f],errors='coerce').dropna().to_numpy(float)
            if not len(x) or not len(y):continue
            stats[f]={'sgcc_median':float(np.median(x)),'ceew_median':float(np.median(y)),
              'wasserstein_distance':float(wasserstein_distance(x,y)),
              'sgcc_q05_q95':[float(np.quantile(x,.05)),float(np.quantile(x,.95))],
              'ceew_q05_q95':[float(np.quantile(y,.05)),float(np.quantile(y,.95))],
              'psi_reference_sgcc':_psi(x,y)}
        report['utilities'][loc]={'source_file':path.name,'meter_count':int(len(cf)),
          'daily_rows':int(len(daily)),'date_start':str(daily.date.min().date()),'date_end':str(daily.date.max().date()),
          'features_compared':len(stats),'statistics':stats}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'output':str(a.output),'sgcc_customers':report['sgcc_customers'],
      'utilities':{k:{'meters':v['meter_count'],'features':v['features_compared']} for k,v in report['utilities'].items()},
      'label_status':report['label_status']},indent=2))
if __name__=='__main__':main()
