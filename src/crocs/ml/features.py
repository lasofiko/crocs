from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import numpy as np
import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS
from crocs.ml.russian_calendar import add_russian_calendar_features
from crocs.ml.weather import add_weather_features

MODEL_TRAIN_START = pd.Timestamp("2022-09-22")
SALARY_DAYS = (5, 10, 15, 20, 25, 30)


def prepare_hourly_series(
    train: pd.DataFrame,
    hours: Iterable[int] | None = None,
) -> pd.DataFrame:
    missing = set(FORECAST_COLUMNS) - set(train.columns)
    if missing:
        raise ValueError(f"train missing columns: {sorted(missing)}")

    prepared = train[list(FORECAST_COLUMNS)].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    prepared["guests_count"] = prepared["guests_count"].astype(float)
    prepared = prepared[prepared["sale_date"] >= MODEL_TRAIN_START].copy()

    if prepared.empty:
        raise ValueError(f"train has no rows on or after {MODEL_TRAIN_START.date()}")

    if hours is None:
        sale_hour = cast(pd.Series, prepared["sale_hour"])
        hours = sorted(sale_hour.unique().tolist())

    full_index = pd.MultiIndex.from_product(
        [
            pd.date_range(prepared["sale_date"].min(), prepared["sale_date"].max(), freq="D"),
            list(hours),
        ],
        names=["sale_date", "sale_hour"],
    )

    prepared = prepared.set_index(["sale_date", "sale_hour"]).reindex(full_index).reset_index()
    return prepared.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)


def add_calendar_features(df: pd.DataFrame) -> pd.DataFrame:
    featured = df.copy()
    featured["sale_date"] = pd.to_datetime(featured["sale_date"], errors="raise")
    featured["sale_hour"] = featured["sale_hour"].astype(int)

    date_series = featured["sale_date"]
    featured["day_of_week"] = date_series.dt.dayofweek
    featured["day_of_month"] = date_series.dt.day
    featured["day_of_year"] = date_series.dt.dayofyear
    featured["week_of_year"] = date_series.dt.isocalendar().week.astype(int)
    featured["month"] = date_series.dt.month
    featured["quarter"] = date_series.dt.quarter
    featured["year"] = date_series.dt.year
    featured["is_weekend"] = featured["day_of_week"].isin([5, 6]).astype(int)

    featured["is_morning_menu"] = (featured["sale_hour"] < 10).astype(int)
    featured["is_main_menu"] = (featured["sale_hour"] >= 10).astype(int)
    featured["is_lunch_hour"] = featured["sale_hour"].between(12, 15).astype(int)
    featured["is_evening_hour"] = featured["sale_hour"].between(18, 21).astype(int)

    featured["hour_sin"] = np.sin(2 * np.pi * featured["sale_hour"] / 24)
    featured["hour_cos"] = np.cos(2 * np.pi * featured["sale_hour"] / 24)
    featured["dow_sin"] = np.sin(2 * np.pi * featured["day_of_week"] / 7)
    featured["dow_cos"] = np.cos(2 * np.pi * featured["day_of_week"] / 7)
    featured["month_sin"] = np.sin(2 * np.pi * featured["month"] / 12)
    featured["month_cos"] = np.cos(2 * np.pi * featured["month"] / 12)

    featured["is_covid_period"] = (
        (date_series >= pd.Timestamp("2020-03-01"))
        & (date_series <= pd.Timestamp("2021-12-31"))
    ).astype(int)
    featured["is_after_rebrand"] = (date_series >= MODEL_TRAIN_START).astype(int)

    featured = add_salary_day_features(featured)
    return add_russian_calendar_features(featured)


def add_salary_day_features(df: pd.DataFrame) -> pd.DataFrame:
    featured = df.copy()
    dates = pd.to_datetime(featured["sale_date"], errors="raise")
    normalized_dates = dates.dt.normalize()
    month_end_day = dates.dt.days_in_month
    unique_dates = pd.Series(normalized_dates.unique())
    salary_day_by_date = {
        current: int(
            current
            in _salary_dates_around(pd.Timestamp(current), months_back=0, months_forward=0)
        )
        for current in unique_dates
    }
    days_to_by_date = {
        current: _days_to_salary(pd.Timestamp(current)) for current in unique_dates
    }
    days_since_by_date = {
        current: _days_since_salary(pd.Timestamp(current)) for current in unique_dates
    }

    featured["is_salary_day"] = normalized_dates.map(salary_day_by_date).astype(int)
    featured["days_to_salary_day"] = normalized_dates.map(days_to_by_date).astype(int)
    featured["days_since_salary_day"] = normalized_dates.map(days_since_by_date).astype(int)
    featured["is_salary_window_2d"] = (
        (featured["days_to_salary_day"] <= 2) | (featured["days_since_salary_day"] <= 2)
    ).astype(int)
    featured["is_month_end_salary_window"] = (dates.dt.day >= (month_end_day - 2)).astype(int)
    return featured


def _salary_dates_around(
    current: pd.Timestamp,
    *,
    months_back: int = 1,
    months_forward: int = 1,
) -> set[pd.Timestamp]:
    current = current.normalize()
    salary_dates: set[pd.Timestamp] = set()
    for offset in range(-months_back, months_forward + 1):
        month_start = current.replace(day=1) + pd.DateOffset(months=offset)
        days_in_month = int(month_start.days_in_month)
        for salary_day in SALARY_DAYS:
            salary_dates.add(
                pd.Timestamp(
                    year=month_start.year,
                    month=month_start.month,
                    day=min(salary_day, days_in_month),
                )
            )
    return salary_dates


def _days_to_salary(current: pd.Timestamp) -> int:
    current = current.normalize()
    candidates = [
        int((salary_date - current).days)
        for salary_date in _salary_dates_around(current)
        if salary_date >= current
    ]
    return min(candidates) if candidates else 31


def _days_since_salary(current: pd.Timestamp) -> int:
    current = current.normalize()
    candidates = [
        int((current - salary_date).days)
        for salary_date in _salary_dates_around(current)
        if salary_date <= current
    ]
    return min(candidates) if candidates else 31


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    featured = df.sort_values(["sale_hour", "sale_date"]).copy()
    grouped = featured.groupby("sale_hour", group_keys=False)["guests_count"]

    featured["lag_7d"] = grouped.shift(7)
    featured["lag_14d"] = grouped.shift(14)
    featured["lag_28d"] = grouped.shift(28)
    featured["lag_364d"] = grouped.shift(364)
    featured["rolling_7d_mean"] = grouped.transform(
        lambda series: series.shift(1).rolling(7, min_periods=3).mean()
    )
    featured["rolling_28d_mean"] = grouped.transform(
        lambda series: series.shift(1).rolling(28, min_periods=7).mean()
    )
    featured["rolling_7d_to_28d_ratio"] = (
        featured["rolling_7d_mean"] / featured["rolling_28d_mean"]
    ).replace([np.inf, -np.inf], np.nan)

    return featured.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)


def build_supervised_frame(
    train: pd.DataFrame,
    hours: Iterable[int] | None = None,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    series = prepare_hourly_series(train, hours=hours)
    featured = add_calendar_features(series)
    featured = add_weather_features(featured, weather)
    featured = add_lag_features(featured)
    span_days = (featured["sale_date"].max() - featured["sale_date"].min()).days + 1

    subset = ["guests_count"]
    for lag, need_days in (
        ("lag_7d", 8),
        ("lag_14d", 15),
        ("lag_28d", 29),
    ):
        if span_days >= need_days:
            subset.append(lag)
    return featured.dropna(subset=subset)
