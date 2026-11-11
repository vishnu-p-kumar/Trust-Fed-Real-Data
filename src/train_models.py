from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split

from src.demand_forecasting import forecast_horizons, train_lstm_forecaster
from src.feature_engineering import build_feature_matrix
from src.federated.partition import stratified_group_holdout
from src.model_optimizer import load_best_hyperparameters
from src.preprocess import load_dataset, load_training_dataset
from src.transformer_forecasting import forecast_transformer_horizons, train_transformer_forecaster
from utils.helpers import ensure_project_dirs, save_joblib, save_json

try:  # pragma: no cover - optional at runtime
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional at runtime
    XGBClassifier = None


def _build_boost_model(seed: int = 42, learning_rate: float = 0.08) -> tuple[Any, str]:
    if XGBClassifier is not None:
        return (
            XGBClassifier(
                n_estimators=220,
                max_depth=6,
                learning_rate=learning_rate,
                subsample=0.85,
                colsample_bytree=0.9,
                objective="binary:logistic",
                eval_metric="logloss",
                random_state=seed,
            ),
            "xgboost",
        )
    return (
        HistGradientBoostingClassifier(
            learning_rate=learning_rate,
            max_depth=8,
            max_iter=260,
            random_state=seed,
        ),
        "hist_gradient_boosting_fallback",
    )


def _predict_probability(model: Any, features: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]
    if hasattr(model, "decision_function"):
        decision = model.decision_function(features)
        return 1.0 / (1.0 + np.exp(-decision))
    prediction = model.predict(features)
    return np.asarray(prediction, dtype=float)


def train_all_models(
    dataset_path: str | Path | None = None,
    max_rows: int = 60000,
    forecast_epochs: int = 5,
    seed: int = 42,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    dataframe = load_dataset(dataset_path) if dataset_path else load_training_dataset(max_rows=max_rows)
    if dataframe.empty:
        raise RuntimeError("Training dataset is empty. Generate synthetic data before training models.")

    if len(dataframe) > max_rows:
        dataframe = load_training_dataset(max_rows=max_rows)

    enriched, features = build_feature_matrix(dataframe)
    target = enriched["is_theft"].astype(int)
    optimized_params = load_best_hyperparameters()
    contamination = float(optimized_params.get("isolation_forest", {}).get("contamination", max(0.03, float(target.mean()))))
    rf_depth = int(optimized_params.get("random_forest", {}).get("max_depth", 16))
    boost_learning_rate = float(optimized_params.get("xgboost", {}).get("learning_rate", 0.08))

    # Customer-disjoint holdout avoids neighboring readings from one meter appearing
    # in both train and test. The test rows remain unused for fitting and tuning.
    if "meter_id" in enriched:
        train_idx, test_idx = stratified_group_holdout(target.to_numpy(), enriched["meter_id"].astype(str).to_numpy(),
                                                       test_size=.2, seed=seed)
        x_train, x_test = features.iloc[train_idx], features.iloc[test_idx]
        y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]
        split_method = "meter_group_holdout"
    else:
        stratify = target if target.nunique() > 1 else None
        x_train, x_test, y_train, y_test = train_test_split(
            features, target, test_size=0.2, random_state=seed, stratify=stratify
        )
        split_method = "stratified_row_fallback"

    normal_subset = x_train.loc[y_train == 0]
    anomaly_training_frame = normal_subset if not normal_subset.empty else x_train
    anomaly_model = IsolationForest(
        n_estimators=220,
        contamination=contamination,
        random_state=seed,
    )
    anomaly_model.fit(anomaly_training_frame)
    anomaly_reference = -anomaly_model.score_samples(anomaly_training_frame)
    anomaly_threshold = float(np.quantile(anomaly_reference, 0.97))

    rf_model = RandomForestClassifier(
        n_estimators=240,
        max_depth=rf_depth,
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=seed,
        n_jobs=-1,
    )
    rf_model.fit(x_train, y_train)

    boost_model, boost_name = _build_boost_model(seed, learning_rate=boost_learning_rate)
    boost_model.fit(x_train, y_train)

    rf_probability = _predict_probability(rf_model, x_test)
    boost_probability = _predict_probability(boost_model, x_test)
    combined_probability = 0.45 * rf_probability + 0.55 * boost_probability
    predictions = (combined_probability >= 0.5).astype(int)

    metrics = {
        "accuracy": float(accuracy_score(y_test, predictions)),
        "precision": float(precision_score(y_test, predictions, zero_division=0)),
        "recall": float(recall_score(y_test, predictions, zero_division=0)),
        "f1_score": float(f1_score(y_test, predictions, zero_division=0)),
        "roc_auc": float(roc_auc_score(y_test, combined_probability)) if y_test.nunique() > 1 else 0.5,
        "training_rows": int(len(x_train)),
        "evaluation_rows": int(len(x_test)),
        "feature_count": int(features.shape[1]),
        "boost_model": boost_name,
        "optimizer_method": optimized_params.get("method", "default"),
    }

    save_joblib(anomaly_model, paths.isolation_forest)
    save_joblib(rf_model, paths.random_forest)
    save_joblib(boost_model, paths.xgboost_model)

    metadata = {
        "feature_schema_version": 2,
        "feature_columns": features.columns.tolist(),
        "anomaly_threshold": anomaly_threshold,
        "theft_threshold": 0.5,
        "split_method": split_method,
        "seed": seed,
        "metrics": metrics,
        "boost_model": boost_name,
        "optimizer_params": optimized_params,
    }
    save_json(metadata, paths.model_metadata)

    lstm_metadata = train_lstm_forecaster(
        enriched,
        epochs=forecast_epochs,
        model_path=paths.lstm_model,
        metadata_path=paths.demand_metadata,
    )
    transformer_metadata = train_transformer_forecaster(
        enriched,
        epochs=max(2, min(4, forecast_epochs)),
        model_path=paths.transformer_model,
        metadata_path=paths.transformer_metadata,
    )
    lstm_forecast = forecast_horizons(metadata_path=paths.demand_metadata, model_path=paths.lstm_model)
    transformer_forecast = forecast_transformer_horizons(
        metadata_path=paths.transformer_metadata,
        model_path=paths.transformer_model,
    )
    forecasting_summary = {
        **lstm_forecast,
        "lstm": lstm_forecast,
        "transformer": transformer_forecast,
        "comparison_series": {
            "lstm": lstm_forecast.get("series", []),
            "transformer": transformer_forecast.get("series", []),
        },
        "model_metadata": {
            "lstm": lstm_metadata,
            "transformer": transformer_metadata,
        },
    }

    return {"classification": metrics, "forecasting": forecasting_summary}


if __name__ == "__main__":
    summary = train_all_models()
    print(summary)
