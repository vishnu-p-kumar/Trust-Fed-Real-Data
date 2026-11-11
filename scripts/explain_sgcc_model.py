"""Validation-only permutation importance for interpretable SGCC feature analysis."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input",type=Path,default=Path("datasets/sgcc/processed/sgcc_meter_features.csv.gz"))
    p.add_argument("--seed",type=int,default=71)
    p.add_argument("--max-customers",type=int,default=4000)
    p.add_argument("--output",type=Path,default=Path("reports/research_runs/sgcc_permutation_explanations.json"))
    a=p.parse_args()
    frame=pd.read_csv(a.input,low_memory=False)
    original_rows=len(frame)
    if a.max_customers and len(frame)>a.max_customers:
        frame=pd.concat([g.sample(n=min(len(g),max(1,int(round(a.max_customers*len(g)/len(frame))))),random_state=2026)
                         for _,g in frame.groupby("is_theft")],ignore_index=True).sample(frac=1,random_state=2026).reset_index(drop=True)
    y=frame["is_theft"].astype(int)
    X=frame.drop(columns=["meter_id","is_theft"],errors="ignore").select_dtypes(include=[np.number,"bool"])
    X=X.replace([np.inf,-np.inf],np.nan)
    xfit,xval,yfit,yval=train_test_split(X,y,test_size=.2,random_state=a.seed,stratify=y)
    model=make_pipeline(SimpleImputer(strategy="median",add_indicator=True,keep_empty_features=True),
        ExtraTreesClassifier(n_estimators=120,max_depth=16,min_samples_leaf=3,class_weight="balanced",
          n_jobs=2,random_state=a.seed))
    model.fit(xfit,yfit)
    result=permutation_importance(model,xval,yval,n_repeats=3,random_state=a.seed,
                                  scoring="average_precision",n_jobs=2)
    ranked=sorted([{"feature":str(name),"mean_pr_auc_decrease":float(mean),
                    "std":float(std)} for name,mean,std in zip(X.columns,result.importances_mean,
                                                                result.importances_std)],
                  key=lambda item:item["mean_pr_auc_decrease"],reverse=True)
    output={"method":"permutation importance on validation split; not causal attribution",
      "seed":a.seed,"source_customers":original_rows,"sampled_customers":len(frame),"train_rows":len(xfit),"validation_rows":len(xval),
      "validation_pr_auc":float(model.predict_proba(xval)[:,1].shape[0] and
                                __import__("sklearn.metrics",fromlist=["average_precision_score"]).average_precision_score(
                                    yval,model.predict_proba(xval)[:,1])),
      "top_features":ranked[:20],
      "limitations":["Importance reflects this model and validation distribution, not causal effects.",
        "Permutation can understate importance for correlated features.",
        "Feature importance does not prove electricity theft; it explains model reliance."]}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(output,indent=2,allow_nan=False),encoding="utf-8")
    print(json.dumps({"output":str(a.output),"top_features":ranked[:10]},indent=2))
if __name__=="__main__": main()
