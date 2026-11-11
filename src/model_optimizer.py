from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, IsolationForest, RandomForestClassifier
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import train_test_split

from src.feature_engineering import build_feature_matrix
from src.federated.partition import stratified_group_holdout
from utils.helpers import ensure_project_dirs, load_json, save_json

try:  # pragma: no cover - optional at runtime
    import optuna
except Exception:  # pragma: no cover - optional at runtime
    optuna = None

try:  # pragma: no cover - optional at runtime
    from xgboost import XGBClassifier
except Exception:  # pragma: no cover - optional at runtime
    XGBClassifier = None


DEFAULT_HYPERPARAMETERS = {
    "isolation_forest": {"contamination": 0.05},
    "random_forest": {"max_depth": 16},
    "xgboost": {"learning_rate": 0.08},
    "method": "default",
}


def _predict_probability(model: Any, features: pd.DataFrame) -> np.ndarray:
    if hasattr(model, "predict_proba"):
        return model.predict_proba(features)[:, 1]
    if hasattr(model, "decision_function"):
        decision = model.decision_function(features)
        return 1.0 / (1.0 + np.exp(-decision))
    return np.asarray(model.predict(features), dtype=float)


def _build_boost_model(learning_rate: float, seed: int = 42) -> Any:
    if XGBClassifier is not None:
        return XGBClassifier(
            n_estimators=180,
            max_depth=6,
            learning_rate=learning_rate,
            subsample=0.85,
            colsample_bytree=0.9,
            objective="binary:logistic",
            eval_metric="logloss",
            random_state=seed,
        )
    return HistGradientBoostingClassifier(learning_rate=learning_rate, max_depth=8, max_iter=180, random_state=seed)


def _evaluate_params(features: pd.DataFrame, target: pd.Series, contamination: float, rf_max_depth: int,
                     boost_learning_rate: float, groups: pd.Series | None = None) -> float:
    if groups is not None:
        train_idx, test_idx = stratified_group_holdout(target.to_numpy(), groups.to_numpy(), test_size=.2, seed=42)
        x_train, x_test = features.iloc[train_idx], features.iloc[test_idx]
        y_train, y_test = target.iloc[train_idx], target.iloc[test_idx]
    else:
        stratify = target if target.nunique() > 1 else None
        x_train, x_test, y_train, y_test = train_test_split(
            features, target, test_size=0.2, random_state=42, stratify=stratify,
        )

    anomaly_model = IsolationForest(
        n_estimators=160,
        contamination=float(contamination),
        random_state=42,
    )
    anomaly_model.fit(x_train.loc[y_train == 0] if int((y_train == 0).sum()) >= 10 else x_train)

    rf_model = RandomForestClassifier(
        n_estimators=180,
        max_depth=int(rf_max_depth),
        min_samples_leaf=2,
        class_weight="balanced_subsample",
        random_state=42,
        n_jobs=-1,
    )
    rf_model.fit(x_train, y_train)

    boost_model = _build_boost_model(boost_learning_rate, seed=42)
    boost_model.fit(x_train, y_train)

    rf_probability = _predict_probability(rf_model, x_test)
    boost_probability = _predict_probability(boost_model, x_test)
    anomaly_probability = -anomaly_model.score_samples(x_test)
    if np.ptp(anomaly_probability) > 0:
        anomaly_probability = (anomaly_probability - anomaly_probability.min()) / np.ptp(anomaly_probability)
    combined = 0.25 * anomaly_probability + 0.30 * rf_probability + 0.45 * boost_probability
    predictions = (combined >= 0.5).astype(int)
    if y_test.nunique() > 1:
        roc_auc = float(roc_auc_score(y_test, combined))
    else:
        roc_auc = 0.5
    return 0.55 * float(f1_score(y_test, predictions, zero_division=0)) + 0.45 * roc_auc


def optimize_detection_models(
    dataframe: pd.DataFrame,
    trials: int = 10,
    output_path: str | Path | None = None,
) -> dict[str, Any]:
    paths = ensure_project_dirs()
    output_path = Path(output_path) if output_path else paths.optimizer_params
    if dataframe.empty:
        save_json(DEFAULT_HYPERPARAMETERS, output_path)
        return DEFAULT_HYPERPARAMETERS

    _, features = build_feature_matrix(dataframe)
    target = dataframe["is_theft"].astype(int)
    groups = dataframe["meter_id"].astype(str) if "meter_id" in dataframe else None
    if len(features) < 100 or target.nunique() < 2 or optuna is None:
        save_json(DEFAULT_HYPERPARAMETERS, output_path)
        return DEFAULT_HYPERPARAMETERS

    def objective(trial: Any) -> float:
        contamination = trial.suggest_float("contamination", 0.02, 0.12)
        rf_max_depth = trial.suggest_int("rf_max_depth", 8, 24)
        boost_learning_rate = trial.suggest_float("boost_learning_rate", 0.03, 0.16)
        return _evaluate_params(features, target, contamination, rf_max_depth, boost_learning_rate, groups=groups)

    study = optuna.create_study(direction="maximize", study_name="smart_grid_model_optimization")
    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    best = {
        "isolation_forest": {"contamination": round(float(study.best_params["contamination"]), 4)},
        "random_forest": {"max_depth": int(study.best_params["rf_max_depth"])},
        "xgboost": {"learning_rate": round(float(study.best_params["boost_learning_rate"]), 4)},
        "best_score": round(float(study.best_value), 4),
        "method": "optuna",
    }
    save_json(best, output_path)
    return best


def load_best_hyperparameters(path: str | Path | None = None) -> dict[str, Any]:
    paths = ensure_project_dirs()
    target = Path(path) if path else paths.optimizer_params
    return load_json(target, default=DEFAULT_HYPERPARAMETERS) or DEFAULT_HYPERPARAMETERS
