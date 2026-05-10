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
    "quarter",
    "year",
    "is_weekend",
    "is_morning_menu",
    "is_main_menu",
    "is_lunch_hour",
    "is_evening_hour",
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
    "is_ru_public_holiday",
    "is_ru_preholiday",
    "is_ru_holiday_period",
    "is_may_holiday_season",
    "is_may_day_block",
    "is_victory_day_block",
    "is_ru_long_weekend",
    "holiday_name_code",
    "holiday_block_day_index",
    "holiday_block_length",
    "days_to_may_day",
    "days_since_may_day",
    "days_to_victory_day",
    "days_since_victory_day",
    "days_to_next_ru_holiday",
    "days_since_prev_ru_holiday",
    "is_salary_day",
    "is_salary_window_2d",
    "is_month_end_salary_window",
    "days_to_salary_day",
    "days_since_salary_day",
    "is_covid_period",
    "is_after_rebrand",
    "lag_7d",
    "lag_14d",
    "lag_28d",
    "rolling_7d_mean",
    "rolling_28d_mean",
    "daily_guests_lag_7d",
    "daily_guests_lag_28d",
    "daily_guests_rolling_7d_mean",
    "daily_guests_rolling_28d_mean",
    "has_weather_observation",
    "weather_temp_c",
    "weather_dew_point_c",
    "weather_humidity_pct",
    "weather_effective_temp_c",
    "weather_effective_sun_temp_c",
    "weather_pressure_hpa",
    "weather_station_pressure_hpa",
    "weather_precip_mm",
    "weather_precip_24h_mm",
    "weather_snow_depth_cm",
    "weather_wind_speed_mps",
    "weather_visibility_km",
    "weather_cloud_total_octas",
    "is_weather_precipitation",
    "is_weather_rain",
    "is_weather_snow",
    "is_weather_fog",
    "is_weather_thunderstorm",
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
        n_jobs=1,
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
