from __future__ import annotations

from datetime import date
from typing import cast

import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS

# Лаги не длиннее ~364 дней; без обрезки истории concat в recursive_forecast раздувается и тормозит/OOM.
_HISTORY_LOOKBACK_DAYS = 420
from crocs.exceptions import ForecastError
from crocs.ml.baseline import build_future_calendar
from crocs.ml.features import (
    MODEL_TRAIN_START,
    add_calendar_features,
    add_lag_features,
    build_supervised_frame,
)
from crocs.ml.weather import add_weather_features


def run_ensemble_forecast(
    train: pd.DataFrame,
    *,
    forecast_start: date,
    forecast_end: date,
    open_hour: int,
    close_hour: int,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Train ensemble models on history and produce hourly guests forecast."""
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

    try:
        from crocs.ml.ensemble_model import train_forecast_ensemble
    except ImportError as exc:
        raise ForecastError(
            "Не установлены зависимости ансамбля (xgboost, catboost и др.). "
            "Выполните: pip install -e ."
        ) from exc

    model = train_forecast_ensemble(train_frame)
    future_calendar = build_future_calendar(forecast_start, forecast_end, hours=hours)
    return recursive_forecast(model, normalized, future_calendar, weather=weather)


def run_lightgbm_forecast(
    train: pd.DataFrame,
    *,
    forecast_start: date,
    forecast_end: date,
    open_hour: int,
    close_hour: int,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Backward-compatible wrapper for the ensemble forecast pipeline."""
    return run_ensemble_forecast(
        train,
        forecast_start=forecast_start,
        forecast_end=forecast_end,
        open_hour=open_hour,
        close_hour=close_hour,
        weather=weather,
    )


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


def _trim_history_window(history_frame: pd.DataFrame, *, before_date: pd.Timestamp) -> pd.DataFrame:
    cutoff = before_date - pd.Timedelta(days=_HISTORY_LOOKBACK_DAYS)
    trimmed = history_frame[history_frame["sale_date"] >= cutoff]
    if len(trimmed) == len(history_frame):
        return history_frame
    return trimmed.reset_index(drop=True)


def recursive_forecast(
    model: ForecastEnsemble,
    history: pd.DataFrame,
    target_calendar: pd.DataFrame,
    *,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    from crocs.ml.ensemble_model import predict_forecast_ensemble

    history_frame = _prepare_history(history)
    calendar = _prepare_calendar(target_calendar)
    fc_min = cast(pd.Timestamp, calendar["sale_date"].min())
    history_frame = _trim_history_window(history_frame, before_date=fc_min)
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

        current_prediction = predict_forecast_ensemble(model, current_features)["ensemble"]
        current_output = current_calendar.copy()
        current_output["guests_count"] = (
            current_prediction.round().clip(lower=0).astype(int).to_numpy()
        )
        predictions.append(current_output)

        history_frame = pd.concat([history_frame, current_output], ignore_index=True)
        history_frame = _trim_history_window(
            history_frame,
            before_date=cast(pd.Timestamp, pd.Timestamp(sale_date)),
        )

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
