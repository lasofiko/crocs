from __future__ import annotations

from dataclasses import dataclass
from typing import cast

import lightgbm as lgb
import pandas as pd
from catboost import CatBoostRegressor
from sklearn.ensemble import RandomForestRegressor
from xgboost import XGBRegressor

from crocs.ml.lightgbm_model import FEATURE_COLUMNS, TARGET_COLUMN

BASE_MODEL_NAMES = ("random_forest", "xgboost", "catboost", "lightgbm")


@dataclass
class ForecastEnsemble:
    models: dict[str, object]
    weights: dict[str, float]
    validation_scores: dict[str, float]


def train_forecast_ensemble(
    train_frame: pd.DataFrame,
    *,
    weight_validation_days: int = 7,
) -> ForecastEnsemble:
    missing = set((*FEATURE_COLUMNS, TARGET_COLUMN)) - set(train_frame.columns)
    if missing:
        raise ValueError(f"train frame missing columns: {sorted(missing)}")

    weights, validation_scores = _estimate_model_weights(
        train_frame,
        validation_days=weight_validation_days,
    )
    features = prepare_features(train_frame)
    target = train_frame[TARGET_COLUMN].astype(float)
    models = _build_base_models()

    for model in models.values():
        model.fit(features, target)

    return ForecastEnsemble(
        models=models,
        weights=weights,
        validation_scores=validation_scores,
    )


def _build_base_models() -> dict[str, object]:
    return {
        "random_forest": RandomForestRegressor(
            n_estimators=100,
            max_depth=16,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=1,
        ),
        "xgboost": XGBRegressor(
            objective="reg:squarederror",
            n_estimators=160,
            learning_rate=0.04,
            max_depth=5,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=1,
            missing=float("nan"),
        ),
        "catboost": CatBoostRegressor(
            loss_function="RMSE",
            iterations=180,
            learning_rate=0.04,
            depth=6,
            random_seed=42,
            verbose=False,
            allow_writing_files=False,
            thread_count=1,
        ),
        "lightgbm": lgb.LGBMRegressor(
            objective="regression",
            n_estimators=180,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.9,
            colsample_bytree=0.9,
            random_state=42,
            n_jobs=1,
            verbose=-1,
        ),
    }


def _estimate_model_weights(
    train_frame: pd.DataFrame,
    *,
    validation_days: int,
) -> tuple[dict[str, float], dict[str, float]]:
    split = _time_validation_split(train_frame, validation_days=validation_days)
    if split is None:
        return _equal_weights(), {}

    fit_frame, validation_frame = split
    fit_features = prepare_features(fit_frame)
    fit_target = fit_frame[TARGET_COLUMN].astype(float)
    validation_features = prepare_features(validation_frame)
    validation_target = validation_frame[TARGET_COLUMN].astype(float)

    scores: dict[str, float] = {}
    for name, model in _build_base_models().items():
        model.fit(fit_features, fit_target)
        prediction = pd.Series(model.predict(validation_features), index=validation_frame.index)
        scores[name] = _wape(validation_target, prediction)

    return _inverse_error_weights(scores), scores


def _time_validation_split(
    train_frame: pd.DataFrame,
    *,
    validation_days: int,
) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    frame = train_frame.copy()
    frame["sale_date"] = pd.to_datetime(frame["sale_date"], errors="raise")
    days = sorted(frame["sale_date"].dt.normalize().unique())
    if len(days) <= validation_days + 28:
        return None

    validation_start = cast(pd.Timestamp, days[-validation_days])
    fit_frame = cast(pd.DataFrame, frame[frame["sale_date"] < validation_start])
    validation_frame = cast(pd.DataFrame, frame[frame["sale_date"] >= validation_start])
    if fit_frame.empty or validation_frame.empty:
        return None
    return fit_frame, validation_frame


def _wape(actual: pd.Series, prediction: pd.Series) -> float:
    denominator = float(actual.abs().sum())
    if denominator == 0:
        return float("inf")
    return float((actual - prediction).abs().sum() / denominator)


def _inverse_error_weights(scores: dict[str, float]) -> dict[str, float]:
    valid_scores = {
        name: score for name, score in scores.items() if pd.notna(score) and score > 0
    }
    if not valid_scores:
        return _equal_weights()

    inverse = {name: 1.0 / score for name, score in valid_scores.items()}
    total = sum(inverse.values())
    weights = {name: inverse.get(name, 0.0) / total for name in BASE_MODEL_NAMES}
    return weights


def _equal_weights() -> dict[str, float]:
    weight = 1.0 / len(BASE_MODEL_NAMES)
    return {name: weight for name in BASE_MODEL_NAMES}


def predict_forecast_ensemble(
    ensemble: ForecastEnsemble,
    frame: pd.DataFrame,
) -> pd.DataFrame:
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")

    features = prepare_features(frame)
    predictions = pd.DataFrame(index=frame.index)
    for name in BASE_MODEL_NAMES:
        model = ensemble.models[name]
        predictions[name] = cast(pd.Series, pd.Series(model.predict(features), index=frame.index))

    total_weight = sum(ensemble.weights.values())
    if total_weight <= 0:
        raise ValueError("ensemble weights must have positive sum")

    predictions["ensemble"] = 0.0
    for name in BASE_MODEL_NAMES:
        predictions["ensemble"] += predictions[name] * ensemble.weights[name] / total_weight
    return predictions


def prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    features = frame[list(FEATURE_COLUMNS)].copy()
    return cast(pd.DataFrame, features.apply(pd.to_numeric, errors="coerce"))
