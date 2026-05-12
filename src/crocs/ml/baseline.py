from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import cast

import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS

DEFAULT_HOURS = tuple(range(7, 23))


def build_future_calendar(
    start: date,
    end: date,
    hours: Iterable[int] = DEFAULT_HOURS,
) -> pd.DataFrame:
    """Build the target date-hour grid for forecasting."""
    dates = pd.date_range(start=start, end=end, freq="D")
    rows = [
        {"sale_date": sale_date.date(), "sale_hour": hour}
        for sale_date in dates
        for hour in hours
    ]
    return cast(pd.DataFrame, pd.DataFrame(rows))


def predict_median_by_weekday_hour(
    train: pd.DataFrame,
    future_calendar: pd.DataFrame,
    *,
    window_weeks: int = 12,
) -> pd.DataFrame:
    """Predict guests as the median for each weekday-hour pair in a recent history window."""
    prepared_train = _prepare_train(train)
    prepared_future = _prepare_future_calendar(future_calendar)

    cutoff = prepared_train["sale_date"].max() - pd.Timedelta(weeks=window_weeks)
    recent_train = prepared_train[prepared_train["sale_date"] > cutoff]
    if recent_train.empty:
        recent_train = prepared_train

    grouped = cast(
        pd.DataFrame,
        recent_train.groupby(["day_of_week", "sale_hour"], as_index=False)["guests_count"].median(),
    )
    grouped.columns = ["day_of_week", "sale_hour", "predicted_guests"]

    fallback_by_hour = cast(
        pd.DataFrame,
        recent_train.groupby("sale_hour", as_index=False)["guests_count"].median(),
    )
    fallback_by_hour.columns = ["sale_hour", "fallback_guests"]

    guests_count = cast(pd.Series, recent_train["guests_count"])
    global_fallback = float(cast(float, guests_count.median()))

    forecast = prepared_future.merge(grouped, on=["day_of_week", "sale_hour"], how="left")
    forecast = forecast.merge(fallback_by_hour, on="sale_hour", how="left")
    forecast["guests_count"] = (
        forecast["predicted_guests"].fillna(forecast["fallback_guests"]).fillna(global_fallback)
    )
    forecast["guests_count"] = forecast["guests_count"].round().clip(lower=0).astype(int)
    forecast["sale_date"] = forecast["sale_date"].dt.date

    return cast(pd.DataFrame, forecast[list(FORECAST_COLUMNS)])


def calculate_forecast_metrics(actual: pd.DataFrame, predicted: pd.DataFrame) -> dict[str, float]:
    """Calculate simple validation metrics for a date-hour forecast."""
    merged = actual.merge(
        predicted,
        on=["sale_date", "sale_hour"],
        suffixes=("_actual", "_predicted"),
        how="inner",
    )
    if merged.empty:
        raise ValueError("No overlapping date-hour rows for metrics")

    error = merged["guests_count_actual"] - merged["guests_count_predicted"]
    absolute_error = error.abs()
    squared_error = error.pow(2)
    denominator = float(cast(float, merged["guests_count_actual"].abs().sum()))

    return {
        "mae": float(cast(float, absolute_error.mean())),
        "rmse": float(cast(float, squared_error.mean()) ** 0.5),
        "wape": float(absolute_error.sum() / denominator) if denominator else 0.0,
        "rows": float(len(merged)),
    }


def _prepare_train(train: pd.DataFrame) -> pd.DataFrame:
    missing = set(FORECAST_COLUMNS) - set(train.columns)
    if missing:
        raise ValueError(f"train missing columns: {sorted(missing)}")

    prepared = train[list(FORECAST_COLUMNS)].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    prepared["guests_count"] = prepared["guests_count"].astype(float)
    sale_date = cast(pd.Series, prepared["sale_date"])
    prepared["day_of_week"] = sale_date.dt.dayofweek
    return cast(pd.DataFrame, prepared)


def _prepare_future_calendar(future_calendar: pd.DataFrame) -> pd.DataFrame:
    required_columns = {"sale_date", "sale_hour"}
    missing = required_columns - set(future_calendar.columns)
    if missing:
        raise ValueError(f"future calendar missing columns: {sorted(missing)}")

    prepared = future_calendar[["sale_date", "sale_hour"]].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    sale_date = cast(pd.Series, prepared["sale_date"])
    prepared["day_of_week"] = sale_date.dt.dayofweek
    return cast(pd.DataFrame, prepared)
