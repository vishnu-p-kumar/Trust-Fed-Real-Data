"""Create customer-level leakage-safe summary features from the raw SGCC wide CSV."""
from __future__ import annotations
import argparse, hashlib, json, re, warnings
from pathlib import Path
import numpy as np
import pandas as pd
warnings.filterwarnings('ignore', category=RuntimeWarning, message='Mean of empty slice')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='Degrees of freedom <= 0 for slice')
warnings.filterwarnings('ignore', category=RuntimeWarning, message='All-NaN slice encountered')

def sha256(path: Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def build_features(source: Path) -> tuple[pd.DataFrame, dict]:
    raw=pd.read_csv(source,low_memory=False)
    cols={str(c).strip().lower():c for c in raw.columns}
    id_col=cols.get("cons_no") or cols.get("consno")
    label_col=cols.get("flag")
    if id_col is None or label_col is None:
        raise ValueError("SGCC source must contain CONS_NO and FLAG columns")
    dates=[]
    for c in raw.columns:
        if c in (id_col,label_col): continue
        d=pd.to_datetime(str(c),format="%Y/%m/%d",errors="coerce")
        if pd.notna(d): dates.append((d,c))
    dates.sort(key=lambda x:x[0])
    if len(dates)<300: raise ValueError(f"expected a multi-year daily SGCC profile; found {len(dates)} date columns")
    if raw[id_col].isna().any() or raw[id_col].astype(str).duplicated().any():
        raise ValueError("customer IDs must be non-null and unique")
    y=pd.to_numeric(raw[label_col],errors="coerce")
    if y.isna().any() or not set(y.unique()).issubset({0,1}) or y.nunique()!=2:
        raise ValueError("FLAG must contain both binary classes 0 and 1")
    date_cols=[c for _,c in dates]
    x=raw[date_cols].apply(pd.to_numeric,errors="coerce").to_numpy(dtype=np.float32)
    valid=np.isfinite(x)
    safe=np.where(valid,x,np.nan)
    with np.errstate(invalid="ignore",divide="ignore"):
        feats={
            "mean_kwh":np.nanmean(safe,axis=1),
            "std_kwh":np.nanstd(safe,axis=1),
            "median_kwh":np.nanmedian(safe,axis=1),
            "min_kwh":np.nanmin(safe,axis=1),
            "max_kwh":np.nanmax(safe,axis=1),
            "p10_kwh":np.nanpercentile(safe,10,axis=1),
            "p25_kwh":np.nanpercentile(safe,25,axis=1),
            "p75_kwh":np.nanpercentile(safe,75,axis=1),
            "p90_kwh":np.nanpercentile(safe,90,axis=1),
            "zero_rate":np.sum((x==0)&valid,axis=1)/np.maximum(valid.sum(axis=1),1),
            "missing_rate":1.0-valid.mean(axis=1),
        }
    feats["coefficient_variation"]=feats["std_kwh"]/np.maximum(np.abs(feats["mean_kwh"]),1e-6)
    n=x.shape[1]; quarter=max(1,n//4); half=max(1,n//2)
    date_index=pd.DatetimeIndex([d for d,_ in dates])
    for name,sl in {
        "first_quarter":slice(0,quarter),"second_quarter":slice(quarter,2*quarter),
        "third_quarter":slice(2*quarter,3*quarter),"last_quarter":slice(-quarter,None),
        "first_half":slice(0,half),"second_half":slice(-half,None),
        "first_90d":slice(0,min(90,n)),"last_90d":slice(max(0,n-90),None)
    }.items():
        with np.errstate(invalid="ignore"):
            feats[f"{name}_mean_kwh"]=np.nanmean(safe[:,sl],axis=1)
    feats["last_vs_first_quarter_delta"]=feats["last_quarter_mean_kwh"]-feats["first_quarter_mean_kwh"]
    feats["interquartile_range_kwh"]=feats["p75_kwh"]-feats["p25_kwh"]
    with np.errstate(invalid="ignore",divide="ignore"):
        feats["p90_exceedance_rate"]=np.sum((x>feats["p90_kwh"][:,None])&valid,axis=1)/np.maximum(valid.sum(axis=1),1)
        diff=np.diff(x,axis=1)
        diff_valid=valid[:,1:]&valid[:,:-1]
        diff_safe=np.where(diff_valid,diff,np.nan)
        feats["daily_change_mean"]=np.nanmean(diff_safe,axis=1)
        feats["daily_change_std"]=np.nanstd(diff_safe,axis=1)
        feats["daily_change_abs_mean"]=np.nanmean(np.abs(diff_safe),axis=1)
        weekend_idx=np.where(date_index.dayofweek>=5)[0]
        weekday_idx=np.where(date_index.dayofweek<5)[0]
        feats["weekday_mean_kwh"]=np.nanmean(safe[:,weekday_idx],axis=1)
        feats["weekend_mean_kwh"]=np.nanmean(safe[:,weekend_idx],axis=1)
        # Lag autocorrelation is computed pairwise with missing values excluded.
        for lag in (1,7):
            left=x[:,:-lag]; right=x[:,lag:]
            pair=valid[:,:-lag]&valid[:,lag:]
            count_pair=np.maximum(pair.sum(axis=1),2)
            left_mean=np.where(pair,left,0).sum(axis=1)/count_pair
            right_mean=np.where(pair,right,0).sum(axis=1)/count_pair
            left_center=np.where(pair,left-left_mean[:,None],0)
            right_center=np.where(pair,right-right_mean[:,None],0)
            numerator=np.sum(left_center*right_center,axis=1)
            denominator=np.sqrt(np.sum(left_center**2,axis=1)*np.sum(right_center**2,axis=1))
            feats[f"lag{lag}_autocorrelation"]=numerator/np.maximum(denominator,1e-8)
    # Per-customer least-squares trend over observed readings only.
    t=np.broadcast_to(np.arange(n,dtype=np.float32),(x.shape[0],n))
    count=valid.sum(axis=1).clip(min=1)
    mt=np.where(valid,t,0).sum(axis=1)/count
    mx=np.where(valid,x,0).sum(axis=1)/count
    numerator=np.where(valid,(t-mt[:,None])*(x-mx[:,None]),0).sum(axis=1)
    denominator=np.where(valid,(t-mt[:,None])**2,0).sum(axis=1)
    feats["daily_trend_slope"]=numerator/np.maximum(denominator,1e-8)
    # Month-of-year and calendar-year consumption patterns.
    for month in range(1,13):
        idx=np.where(date_index.month==month)[0]
        with np.errstate(invalid="ignore"):
            feats[f"month_{month:02d}_mean_kwh"]=np.nanmean(safe[:,idx],axis=1)
    for year in sorted(date_index.year.unique()):
        idx=np.where(date_index.year==year)[0]
        with np.errstate(invalid="ignore"):
            feats[f"year_{year}_mean_kwh"]=np.nanmean(safe[:,idx],axis=1)
    out=pd.DataFrame({"meter_id":raw[id_col].astype(str),"is_theft":y.astype("int8")})
    for name,values in feats.items(): out[name]=np.asarray(values,dtype=np.float32)
    out.replace([np.inf,-np.inf],np.nan,inplace=True)
    meta={
        "dataset":"State Grid Corporation of China (SGCC) electricity theft detection benchmark",
        "source_file":source.name,"source_sha256":sha256(source),
        "customers":int(len(raw)),"unique_customers":int(raw[id_col].nunique()),
        "daily_columns":int(len(dates)),"date_start":str(date_index.min().date()),
        "date_end":str(date_index.max().date()),
        "label_counts":{"0":int((y==0).sum()),"1":int((y==1).sum())},
        "missing_reading_rate":float(1-valid.mean()),
        "feature_count":int(len(feats)),
        "feature_method":"per-customer summaries, robust quantiles, zero/missing rates, early/late windows, linear trend, month-of-year and year means; computed without using labels",
        "split_protocol":"one row per customer; customer-disjoint 80/20 holdout; no customer overlap",
        "limitations":["This is historical daily data, not a live stream.",
          "SGCC is a China utility benchmark; metrics do not establish performance on Indian consumers.",
          "The dataset README requests citation but does not state an explicit redistribution licence.",
          "The binary FLAG is a published benchmark label; the uploaded package does not include individual inspection/audit records."],
    }
    return out,meta

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",required=True,type=Path)
    p.add_argument("--output",default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"),type=Path)
    p.add_argument("--manifest",default=Path("datasets/sgcc/processed/feature_manifest.json"),type=Path)
    a=p.parse_args()
    frame,meta=build_features(a.input)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    frame.to_csv(a.output,index=False,compression="gzip" if str(a.output).endswith(".gz") else None)
    meta["processed_file"]=str(a.output)
    meta["processed_sha256"]=sha256(a.output)
    a.manifest.parent.mkdir(parents=True,exist_ok=True)
    a.manifest.write_text(json.dumps(meta,indent=2),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"rows":len(frame),"features":len(frame.columns)-2,
                      "label_counts":meta["label_counts"],"missing_rate":meta["missing_reading_rate"],
                      "manifest":str(a.manifest)},indent=2))
if __name__=="__main__": main()
