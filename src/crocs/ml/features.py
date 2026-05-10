from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS
from crocs.ml.russian_calendar import add_russian_calendar_features


def prepare_hourly_series(
    train: pd.DataFrame,
    hours: Iterable[int] | None = None,
) -> pd.DataFrame:
    """Prepare a regular date-hour series for feature generation."""
    missing = set(FORECAST_COLUMNS) - set(train.columns)
    if missing:
        raise ValueError(f"train missing columns: {sorted(missing)}")

    prepared = train[list(FORECAST_COLUMNS)].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    prepared["guests_count"] = prepared["guests_count"].astype(float)

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
    """Add date and hour features."""
    featured = df.copy()
    featured["sale_date"] = pd.to_datetime(featured["sale_date"], errors="raise")

    date_series = featured["sale_date"]
    featured["day_of_week"] = date_series.dt.dayofweek
    featured["day_of_month"] = date_series.dt.day
    featured["day_of_year"] = date_series.dt.dayofyear
    featured["week_of_year"] = date_series.dt.isocalendar().week.astype(int)
    featured["month"] = date_series.dt.month
    featured["is_weekend"] = featured["day_of_week"].isin([5, 6]).astype(int)
    featured["is_covid_period"] = (
        (date_series >= pd.Timestamp("2020-03-01"))
        & (date_series <= pd.Timestamp("2021-12-31"))
    ).astype(int)
    featured["is_after_rebrand"] = (date_series >= pd.Timestamp("2023-01-01")).astype(int)
    return add_russian_calendar_features(featured)


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add lag and rolling features by hour."""
    featured = df.sort_values(["sale_hour", "sale_date"]).copy()
    grouped = featured.groupby("sale_hour", group_keys=False)["guests_count"]

    featured["lag_7d"] = grouped.shift(7)
    featured["lag_14d"] = grouped.shift(14)
    featured["lag_28d"] = grouped.shift(28)
    featured["lag_56d"] = grouped.shift(56)
    featured["lag_91d"] = grouped.shift(91)
    featured["lag_182d"] = grouped.shift(182)
    featured["lag_364d"] = grouped.shift(364)
    featured["rolling_7d_mean"] = grouped.shift(1).rolling(7, min_periods=3).mean()
    featured["rolling_28d_mean"] = grouped.shift(1).rolling(28, min_periods=7).mean()
    featured["rolling_56d_mean"] = grouped.shift(1).rolling(56, min_periods=14).mean()
    featured["rolling_91d_mean"] = grouped.shift(1).rolling(91, min_periods=21).mean()

    return featured.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)


def build_supervised_frame(
    train: pd.DataFrame,
    hours: Iterable[int] | None = None,
) -> pd.DataFrame:
    """Build a model-ready frame from raw train data."""
    series = prepare_hourly_series(train, hours=hours)
    featured = add_calendar_features(series)
    featured = add_lag_features(featured)
    span_days = (
        featured["sale_date"].max() - featured["sale_date"].min()
    ).days + 1
    # Лаги появляются только после достаточной истории; для коротких рядов не требуем их в dropna.
    subset = ["guests_count"]
    for lag, need_days in (("lag_7d", 8), ("lag_14d", 15), ("lag_28d", 29)):
        if span_days >= need_days:
            subset.append(lag)
    return featured.dropna(subset=subset)
