"""Leakage-aware baseline benchmark for a labeled customer-level theft CSV.

Supports SGCC-style wide tables (one row/customer with d001...d365 columns) and
long tables with one row per reading. Customer groups are split before fitting; the
holdout is never used for fitting or threshold selection. This is a research benchmark,
not a proof that labels are independently verified.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import (accuracy_score, average_precision_score, balanced_accuracy_score, confusion_matrix,
                             f1_score, matthews_corrcoef, precision_score, recall_score, roc_auc_score)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression

LABELS = ("is_theft", "theft_label", "label", "target", "fraud", "flag")
IDS = ("meter_id", "customer_id", "consumer_id", "client_id", "cons_no", "consno", "consumerid", "customer", "id")


def evaluate(frame: pd.DataFrame, seed: int = 42) -> dict:
    normalized = {str(c).strip().lower(): c for c in frame.columns}
    label_col = next((normalized[c] for c in LABELS if c in normalized), None)
    group_col = next((normalized[c] for c in IDS if c in normalized), None)
    if label_col is None or group_col is None:
        raise ValueError("Input must include a binary theft label and customer/meter identifier.")
    data = frame.loc[frame[label_col].notna()].copy()
    y_raw = data[label_col]
    # Accept common numeric and textual binary labels, but refuse ambiguous categories.
    if set(pd.unique(y_raw)).issubset({0, 1, 0.0, 1.0, False, True}):
        y = y_raw.astype(int)
    else:
        mapping = {"normal": 0, "honest": 0, "non-theft": 0, "non_theft": 0, "0": 0,
                   "theft": 1, "fraud": 1, "fraudulent": 1, "1": 1}
        mapped = y_raw.astype(str).str.strip().str.lower().map(mapping)
        if mapped.isna().any():
            raise ValueError("Labels must be binary 0/1 or common normal/theft text values.")
        y = mapped.astype(int)
    if y.nunique() != 2:
        raise ValueError("Both positive and negative labels are required.")
    groups = data[group_col].astype(str)
    splitter = GroupShuffleSplit(n_splits=1, test_size=.2, random_state=seed)
    train_idx, test_idx = next(splitter.split(data, y, groups))
    train, test = data.iloc[train_idx], data.iloc[test_idx]
    y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
    if y_train.nunique() != 2 or y_test.nunique() != 2:
        raise ValueError("Group holdout produced a single-class partition. Use more labeled customers or a different seed.")
    # Exclude target, identifiers, obvious label proxies and non-numeric fields.
    excluded = {label_col, group_col}
    excluded.update(c for c in data.columns if str(c).lower() in {"theft_type", "seeded_theft_probability", "is_anomaly", "target", "label"})
    candidates = data.drop(columns=list(excluded), errors="ignore")
    # SGCC-style tables contain ~1,000 daily readings per customer. Summarize the
    # profile row-wise to avoid a very wide, memory-heavy benchmark and keep all
    # statistics confined to that customer's observed history.
    daily_columns = [column for column in candidates.columns if __import__("re").fullmatch(r"d\d{1,4}", str(column).strip().lower())]
    if len(daily_columns) >= 30:
        profile = candidates[daily_columns].apply(pd.to_numeric, errors="coerce")
        arr = profile.to_numpy(dtype=float)
        finite = np.isfinite(arr)
        safe = np.where(finite, arr, np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            summaries = pd.DataFrame({
                "profile_mean": np.nanmean(safe, axis=1),
                "profile_std": np.nanstd(safe, axis=1),
                "profile_min": np.nanmin(safe, axis=1),
                "profile_max": np.nanmax(safe, axis=1),
                "profile_median": np.nanmedian(safe, axis=1),
                "profile_zero_rate": np.nanmean(np.where(finite, arr == 0, np.nan), axis=1),
                "profile_missing_rate": 1.0 - finite.mean(axis=1),
                "profile_first_quarter_mean": np.nanmean(safe[:, :max(1, arr.shape[1] // 4)], axis=1),
                "profile_last_quarter_mean": np.nanmean(safe[:, -max(1, arr.shape[1] // 4):], axis=1),
            }, index=candidates.index)
        summaries["profile_change_last_vs_first"] = summaries["profile_last_quarter_mean"] - summaries["profile_first_quarter_mean"]
        other = candidates.drop(columns=daily_columns).select_dtypes(include=[np.number, "bool"])
        X = pd.concat([other, summaries], axis=1).replace([np.inf, -np.inf], np.nan)
    else:
        X = candidates.select_dtypes(include=[np.number, "bool"]).replace([np.inf, -np.inf], np.nan)
    if X.empty:
        raise ValueError("No numeric model features remain after excluding labels and identifiers.")
    X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
    models = {
        "logistic_regression": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced", random_state=seed)),
        "random_forest": make_pipeline(SimpleImputer(strategy="median"), RandomForestClassifier(n_estimators=150, max_depth=16, max_features="sqrt", class_weight="balanced_subsample", min_samples_leaf=5, random_state=seed, n_jobs=2)),
        "hist_gradient_boosting": make_pipeline(SimpleImputer(strategy="median"), HistGradientBoostingClassifier(max_iter=150, learning_rate=.08, l2_regularization=1.0, random_state=seed)),
    }
    results = {}
    for name, model in models.items():
        model.fit(X_train, y_train)
        probability = model.predict_proba(X_test)[:, 1]
        # Fixed threshold avoids selecting a threshold on the test set.
        prediction = (probability >= .5).astype(int)
        tn, fp, fn, tp = confusion_matrix(y_test, prediction, labels=[0, 1]).ravel()
        results[name] = {
            "accuracy": float(accuracy_score(y_test, prediction)),
            "precision": float(precision_score(y_test, prediction, zero_division=0)),
            "recall": float(recall_score(y_test, prediction, zero_division=0)),
            "f1": float(f1_score(y_test, prediction, zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, prediction)),
            "roc_auc": float(roc_auc_score(y_test, probability)),
            "average_precision": float(average_precision_score(y_test, probability)),
            "false_positive_rate": float(fp / max(1, fp + tn)),
            "mcc": float(matthews_corrcoef(y_test, prediction)),
            "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
        }
    overlap = set(groups.iloc[train_idx]).intersection(set(groups.iloc[test_idx]))
    if overlap:
        raise AssertionError("Customer leakage detected between train and test groups")
    return {"protocol": "single customer-disjoint 80/20 holdout; threshold=0.5 fixed before test evaluation",
            "seed": seed, "rows": len(data), "features": list(map(str, X.columns)),
            "train_rows": len(train), "test_rows": len(test), "train_customers": int(groups.iloc[train_idx].nunique()),
            "test_customers": int(groups.iloc[test_idx].nunique()), "customer_overlap": 0,
            "positive_rate_train": float(y_train.mean()), "positive_rate_test": float(y_test.mean()),
            "metrics": results,
            "warning": "Evaluation quality depends on label provenance and dataset representativeness; scores do not validate the labels themselves."}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", type=Path, default=Path("reports/research_runs/theft_benchmark.json"))
    args = parser.parse_args()
    result = evaluate(pd.read_csv(args.input, low_memory=False), args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
    print(json.dumps(result, indent=2, allow_nan=False))

if __name__ == "__main__":
    main()
