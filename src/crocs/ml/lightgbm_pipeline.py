from __future__ import annotations

from datetime import date
from typing import cast

import lightgbm as lgb
import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS
from crocs.exceptions import ForecastError
from crocs.ml.baseline import build_future_calendar
from crocs.ml.features import (
    MODEL_TRAIN_START,
    add_calendar_features,
    add_lag_features,
    build_supervised_frame,
)
from crocs.ml.lightgbm_model import predict_lightgbm, train_lightgbm
from crocs.ml.weather import add_weather_features


def run_lightgbm_forecast(
    train: pd.DataFrame,
    *,
    forecast_start: date,
    forecast_end: date,
    open_hour: int,
    close_hour: int,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Train LightGBM on history and produce hourly guests forecast for the date range."""
    if train.empty:
        raise ForecastError("train is empty")

    normalized = _normalize_train(train)
    _require_forecast_columns(normalized)
    normalized["sale_date"] = pd.to_datetime(normalized["sale_date"], errors="raise")
    normalized = normalized[normalized["sale_date"] >= MODEL_TRAIN_START].copy()
    if normalized.empty:
        raise ForecastError(f"train has no rows on or after {MODEL_TRAIN_START.date()}")

    if open_hour >= close_hour:
        raise ForecastError(
            "Need open_hour < close_hour; last sale_hour = close_hour - 1 "
            "(restaurant closes at close_hour).",
        )
    hours = tuple(range(open_hour, close_hour))
    train_frame = build_supervised_frame(normalized, hours=hours, weather=weather)
    if train_frame.empty:
        raise ForecastError(
            "Train frame is empty after feature preparation: not enough history for lags "
            "or all rows were filtered out."
        )

    model = train_lightgbm(train_frame)
    future_calendar = build_future_calendar(forecast_start, forecast_end, hours=hours)
    return recursive_forecast(model, normalized, future_calendar, weather=weather)


def _normalize_train(train: pd.DataFrame) -> pd.DataFrame:
    t = train.copy()
    t.columns = [str(c).strip().lower() for c in t.columns]
    return t


def _require_forecast_columns(frame: pd.DataFrame) -> None:
    need = set(FORECAST_COLUMNS)
    missing = need - set(frame.columns)
    if missing:
        raise ForecastError(f"train is missing columns: {sorted(missing)}")

    t = frame.copy()
    t["sale_date"] = pd.to_datetime(t["sale_date"], errors="coerce")
    if t["sale_date"].isna().any():
        raise ForecastError("train has invalid sale_date values")


def recursive_forecast(
    model: lgb.LGBMRegressor,
    history: pd.DataFrame,
    target_calendar: pd.DataFrame,
    *,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    history_frame = _prepare_history(history)
    calendar = _prepare_calendar(target_calendar)
    predictions: list[pd.DataFrame] = []

    for sale_date in sorted(cast(pd.Series, calendar["sale_date"]).unique().tolist()):
        current_calendar = cast(pd.DataFrame, calendar[calendar["sale_date"] == sale_date].copy())
        current_rows = current_calendar.copy()
        current_rows["guests_count"] = pd.NA

        combined = pd.concat([history_frame, current_rows], ignore_index=True)
        featured = add_calendar_features(combined)
        featured = add_weather_features(featured, weather)
        featured = add_lag_features(featured)
        current_features = cast(pd.DataFrame, featured[featured["sale_date"] == sale_date].copy())

        current_prediction = predict_lightgbm(model, current_features)
        current_output = current_calendar.copy()
        current_output["guests_count"] = (
            current_prediction.round().clip(lower=0).astype(int).to_numpy()
        )
        predictions.append(current_output)

        history_frame = pd.concat([history_frame, current_output], ignore_index=True)

    forecast = pd.concat(predictions, ignore_index=True)
    sale_date_series = cast(pd.Series, forecast["sale_date"])
    forecast["sale_date"] = pd.to_datetime(sale_date_series).dt.date
    return cast(pd.DataFrame, forecast[list(FORECAST_COLUMNS)])


def _prepare_history(history: pd.DataFrame) -> pd.DataFrame:
    prepared = history[["sale_date", "sale_hour", "guests_count"]].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    prepared["guests_count"] = prepared["guests_count"].astype(float)
    return cast(pd.DataFrame, prepared)


def _prepare_calendar(target_calendar: pd.DataFrame) -> pd.DataFrame:
    prepared = target_calendar[["sale_date", "sale_hour"]].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    return cast(pd.DataFrame, prepared)
