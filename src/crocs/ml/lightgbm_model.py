from __future__ import annotations

from typing import cast

import lightgbm as lgb
import pandas as pd

FEATURE_COLUMNS = (
    "sale_hour",
    "day_of_week",
    "day_of_month",
    "day_of_year",
    "week_of_year",
    "month",
    "is_weekend",
    "is_ru_public_holiday",
    "is_ru_preholiday",
    "is_ru_holiday_period",
    "is_may_holiday_season",
    "days_since_may_day",
    "days_to_next_ru_holiday",
    "days_since_prev_ru_holiday",
    "is_covid_period",
    "is_after_rebrand",
    "lag_7d",
    "lag_14d",
    "lag_28d",
    "lag_56d",
    "lag_91d",
    "lag_182d",
    "lag_364d",
    "rolling_7d_mean",
    "rolling_28d_mean",
    "rolling_56d_mean",
    "rolling_91d_mean",
)
TARGET_COLUMN = "guests_count"


def train_lightgbm(train_frame: pd.DataFrame) -> lgb.LGBMRegressor:
    missing = set((*FEATURE_COLUMNS, TARGET_COLUMN)) - set(train_frame.columns)
    if missing:
        raise ValueError(f"train frame missing columns: {sorted(missing)}")

    features = _prepare_features(train_frame)
    model = lgb.LGBMRegressor(
        objective="regression",
        n_estimators=300,
        learning_rate=0.05,
        num_leaves=31,
        subsample=0.9,
        colsample_bytree=0.9,
        random_state=42,
        verbose=-1,
    )
    model.fit(features, train_frame[TARGET_COLUMN].astype(float))
    return model


def predict_lightgbm(model: lgb.LGBMRegressor, frame: pd.DataFrame) -> pd.Series:
    missing = set(FEATURE_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"prediction frame missing columns: {sorted(missing)}")

    prediction = model.predict(_prepare_features(frame))
    return pd.Series(prediction, index=frame.index, name="guests_count")


def _prepare_features(frame: pd.DataFrame) -> pd.DataFrame:
    features = frame[list(FEATURE_COLUMNS)].copy()
    return cast(pd.DataFrame, features.apply(pd.to_numeric, errors="coerce"))
