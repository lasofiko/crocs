from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from catboost import CatBoostRegressor

from crocs.config import RESTAURANT_CLOSE_HOUR, RESTAURANT_OPEN_HOUR
from crocs.ml.baseline import build_future_calendar
from crocs.ml.features import (
    MODEL_TRAIN_START,
    add_calendar_features,
    add_lag_features,
    prepare_hourly_series,
)
from crocs.ml.russian_calendar import FIXED_PUBLIC_HOLIDAYS, OFFICIAL_2026_NON_WORKING_DAYS
from crocs.ml.weather import add_weather_features

HOURS_DEFAULT = tuple(range(RESTAURANT_OPEN_HOUR, RESTAURANT_CLOSE_HOUR))
TARGET_COLUMN = "guests_count"

HISTORICAL_NON_WORKING_DAYS: set[date] = set()
for d in range(1, 9):
    HISTORICAL_NON_WORKING_DAYS.add(date(2023, 1, d))
HISTORICAL_NON_WORKING_DAYS |= {
    date(2023, 2, 23), date(2023, 2, 24), date(2023, 2, 25), date(2023, 2, 26),
    date(2023, 3, 8),
    date(2023, 4, 29), date(2023, 4, 30), date(2023, 5, 1),
    date(2023, 5, 6), date(2023, 5, 7), date(2023, 5, 8), date(2023, 5, 9),
    date(2023, 6, 10), date(2023, 6, 11), date(2023, 6, 12),
    date(2023, 11, 4), date(2023, 11, 5), date(2023, 11, 6),
    date(2023, 12, 31),
}
for d in range(1, 9):
    HISTORICAL_NON_WORKING_DAYS.add(date(2024, 1, d))
HISTORICAL_NON_WORKING_DAYS |= {
    date(2024, 2, 23), date(2024, 2, 24), date(2024, 2, 25),
    date(2024, 3, 8), date(2024, 3, 9), date(2024, 3, 10),
    date(2024, 4, 29), date(2024, 4, 30), date(2024, 5, 1),
    date(2024, 5, 9), date(2024, 5, 10), date(2024, 5, 11), date(2024, 5, 12),
    date(2024, 6, 12),
    date(2024, 11, 2), date(2024, 11, 3), date(2024, 11, 4),
    date(2024, 12, 28), date(2024, 12, 29), date(2024, 12, 30), date(2024, 12, 31),
}
for d in range(1, 9):
    HISTORICAL_NON_WORKING_DAYS.add(date(2025, 1, d))
HISTORICAL_NON_WORKING_DAYS |= {
    date(2025, 2, 22), date(2025, 2, 23), date(2025, 2, 24),
    date(2025, 3, 8), date(2025, 3, 9),
    date(2025, 5, 1), date(2025, 5, 2), date(2025, 5, 3), date(2025, 5, 4),
    date(2025, 5, 8), date(2025, 5, 9), date(2025, 5, 10), date(2025, 5, 11),
    date(2025, 6, 12), date(2025, 6, 13), date(2025, 6, 14), date(2025, 6, 15),
    date(2025, 11, 2), date(2025, 11, 3), date(2025, 11, 4),
    date(2025, 12, 31),
}


BASE_TIME = ["sale_hour", "day_of_week", "day_of_month", "day_of_year",
             "week_of_year", "month", "is_weekend"]
BASE_HOLIDAYS = ["is_ru_public_holiday", "is_ru_preholiday", "is_ru_holiday_period",
                 "is_may_day_block", "is_victory_day_block", "holiday_name_code",
                 "holiday_block_day_index", "holiday_block_length",
                 "days_to_may_day", "days_since_may_day",
                 "days_to_victory_day", "days_since_victory_day",
                 "days_to_next_ru_holiday", "days_since_prev_ru_holiday"]
BASE_LAGS = ["lag_7d", "lag_14d", "lag_28d", "lag_364d",
             "rolling_7d_mean", "rolling_28d_mean", "rolling_7d_to_28d_ratio"]
EXTRA_HOLIDAY = ["is_day_before_state_holiday", "is_2_days_before_state_holiday",
                 "is_day_after_state_holiday", "is_short_work_week"]
BREAK_DAYS = ["upcoming_break_days", "past_break_days", "is_bridge_day"]
WEATHER_LAGS = ["weather_temp_lag_7d", "weather_temp_lag_364d",
                "weather_precip_lag_7d", "weather_precip_lag_364d"]

TABULAR = BASE_TIME + BASE_HOLIDAYS + BASE_LAGS + EXTRA_HOLIDAY + BREAK_DAYS + WEATHER_LAGS
CATS = ["day_of_week", "month", "holiday_name_code", "sale_hour",
        "holiday_block_day_index", "holiday_block_length",
        "upcoming_break_days", "past_break_days"]


def _is_state_holiday(d: pd.Timestamp) -> bool:
    return (d.month, d.day) in FIXED_PUBLIC_HOLIDAYS


def _is_non_working(d: pd.Timestamp) -> bool:
    if _is_state_holiday(d):
        return True
    if d.dayofweek >= 5:
        return True
    d_date = d.date() if hasattr(d, "date") else d
    return d_date in OFFICIAL_2026_NON_WORKING_DAYS or d_date in HISTORICAL_NON_WORKING_DAYS


def upcoming_break_days(d: pd.Timestamp, max_horizon: int = 14) -> int:
    count = 0
    for delta in range(1, max_horizon + 1):
        if _is_non_working(d + pd.Timedelta(days=delta)):
            count += 1
        else:
            break
    return count


def past_break_days(d: pd.Timestamp, max_horizon: int = 14) -> int:
    count = 0
    for delta in range(1, max_horizon + 1):
        if _is_non_working(d - pd.Timedelta(days=delta)):
            count += 1
        else:
            break
    return count


def is_bridge_day(d: pd.Timestamp) -> int:
    if _is_non_working(d):
        return 0
    return int(_is_non_working(d - pd.Timedelta(days=1))
               and _is_non_working(d + pd.Timedelta(days=1)))


def add_break_features(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    dates = pd.to_datetime(work["sale_date"])
    next_1 = dates + pd.Timedelta(days=1)
    next_2 = dates + pd.Timedelta(days=2)
    prev_1 = dates - pd.Timedelta(days=1)

    work["is_day_before_state_holiday"] = next_1.apply(_is_state_holiday).astype(int)
    work["is_2_days_before_state_holiday"] = next_2.apply(_is_state_holiday).astype(int)
    work["is_day_after_state_holiday"] = prev_1.apply(_is_state_holiday).astype(int)

    iso_y, iso_w = dates.dt.isocalendar().year, dates.dt.isocalendar().week
    weeks_with_holiday: set = set()
    for d in pd.Series(dates.unique()):
        if _is_state_holiday(d):
            iso = d.isocalendar()
            weeks_with_holiday.add((iso.year, iso.week))
    work["is_short_work_week"] = pd.Series(
        [(y, w) in weeks_with_holiday for y, w in zip(iso_y, iso_w, strict=False)],
        index=work.index,
    ).astype(int)

    unique_dates = dates.dt.normalize().unique()
    up_map = {d: upcoming_break_days(pd.Timestamp(d)) for d in unique_dates}
    past_map = {d: past_break_days(pd.Timestamp(d)) for d in unique_dates}
    bridge_map = {d: is_bridge_day(pd.Timestamp(d)) for d in unique_dates}

    norm = dates.dt.normalize()
    work["upcoming_break_days"] = norm.map(up_map).astype(int)
    work["past_break_days"] = norm.map(past_map).astype(int)
    work["is_bridge_day"] = norm.map(bridge_map).astype(int)
    return work


def interpolate_weather(weather_raw: pd.DataFrame) -> pd.DataFrame:
    if weather_raw is None or weather_raw.empty:
        return weather_raw
    work = weather_raw.copy()
    work["sale_date"] = pd.to_datetime(work["sale_date"])
    work["sale_hour"] = work["sale_hour"].astype(int)
    all_dates = pd.date_range(work["sale_date"].min(), work["sale_date"].max(), freq="D")
    full_idx = pd.MultiIndex.from_product([all_dates, range(0, 24)],
                                          names=["sale_date", "sale_hour"])
    work = work.set_index(["sale_date", "sale_hour"]).reindex(full_idx).reset_index()
    cols = [c for c in ["temp_c", "precipitation_mm"] if c in work.columns]
    work[cols] = work.groupby("sale_date")[cols].ffill(limit=3)
    work[cols] = work.groupby("sale_date")[cols].bfill(limit=3)
    return work.dropna(subset=["temp_c"])


def add_lagged_weather(df: pd.DataFrame, weather_interp: pd.DataFrame) -> pd.DataFrame:
    if weather_interp is None or weather_interp.empty:
        for col in WEATHER_LAGS:
            df[col] = np.nan
        return df
    work = df.copy()
    work["sale_date"] = pd.to_datetime(work["sale_date"])
    work["sale_hour"] = work["sale_hour"].astype(int)
    w = weather_interp[["sale_date", "sale_hour", "temp_c", "precipitation_mm"]].copy()
    w["sale_date"] = pd.to_datetime(w["sale_date"])
    for lag_days in [7, 364]:
        w_lag = w.copy()
        w_lag["sale_date"] = w_lag["sale_date"] + pd.Timedelta(days=lag_days)
        w_lag = w_lag.rename(columns={
            "temp_c": f"weather_temp_lag_{lag_days}d",
            "precipitation_mm": f"weather_precip_lag_{lag_days}d",
        })
        work = work.merge(w_lag, on=["sale_date", "sale_hour"], how="left")
    return work


def build_frame(train: pd.DataFrame, weather_interp: pd.DataFrame,
                hours: tuple = HOURS_DEFAULT) -> pd.DataFrame:
    series = prepare_hourly_series(train, hours=hours)
    f = add_calendar_features(series)
    f = add_weather_features(f, weather_interp)
    f = add_lag_features(f)
    f = add_break_features(f)
    f = add_lagged_weather(f, weather_interp)
    return f.dropna(subset=["guests_count", "lag_7d", "lag_14d", "lag_28d"]).reset_index(drop=True)


def make_sample_weights(frame: pd.DataFrame) -> np.ndarray:
    dates = pd.to_datetime(frame["sale_date"])
    cutoff = dates.max() - pd.Timedelta(days=180)
    w = np.ones(len(frame))
    w[dates >= cutoff] = 2.0
    in_may = (dates >= "2025-04-27") & (dates <= "2025-05-04")
    w[in_may] = 3.0
    return w


def prep_for_cat(frame: pd.DataFrame) -> pd.DataFrame:
    feat = frame[TABULAR].copy()
    for c in CATS:
        feat[c] = feat[c].astype(int)
    for c in feat.columns:
        if c not in CATS:
            feat[c] = pd.to_numeric(feat[c], errors="coerce").fillna(-9999)
    return feat


def train_model(train_frame: pd.DataFrame, weights: np.ndarray | None = None,
                seed: int = 42) -> CatBoostRegressor:
    cat_idx = [TABULAR.index(c) for c in CATS]
    model = CatBoostRegressor(
        loss_function="MAE",
        iterations=600,
        learning_rate=0.05,
        depth=7,
        random_seed=seed,
        cat_features=cat_idx,
        verbose=False,
        allow_writing_files=False,
        thread_count=1,
    )
    if weights is None:
        weights = make_sample_weights(train_frame)
    model.fit(prep_for_cat(train_frame),
              train_frame[TARGET_COLUMN].astype(float),
              sample_weight=weights)
    return model


def predict_recursive(model: CatBoostRegressor, history: pd.DataFrame,
                      calendar: pd.DataFrame, weather_interp: pd.DataFrame) -> pd.DataFrame:
    history_frame = history[["sale_date", "sale_hour", "guests_count"]].copy()
    history_frame["sale_date"] = pd.to_datetime(history_frame["sale_date"])
    cal = calendar[["sale_date", "sale_hour"]].copy()
    cal["sale_date"] = pd.to_datetime(cal["sale_date"])

    predictions: list[pd.DataFrame] = []
    for sale_date in sorted(cal["sale_date"].unique()):
        current = cal[cal["sale_date"] == sale_date].copy()
        current_aug = current.copy()
        current_aug["guests_count"] = pd.NA
        combined = pd.concat([history_frame, current_aug], ignore_index=True)

        f = add_calendar_features(combined)
        f = add_weather_features(f, weather_interp)
        f = add_lag_features(f)
        f = add_break_features(f)
        f = add_lagged_weather(f, weather_interp)

        today = f[f["sale_date"] == sale_date].copy()
        pred = model.predict(prep_for_cat(today))
        out = current.copy()
        out["guests_count"] = np.clip(np.round(pred), 0, None).astype(int)
        predictions.append(out)
        history_frame = pd.concat([history_frame, out], ignore_index=True)
    return pd.concat(predictions, ignore_index=True)


def run_forecast(
    train: pd.DataFrame,
    *,
    forecast_start: date,
    forecast_end: date,
    open_hour: int = RESTAURANT_OPEN_HOUR,
    close_hour: int = RESTAURANT_CLOSE_HOUR,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    if train.empty:
        raise ValueError("train is empty")

    normalized = train.copy()
    normalized.columns = [str(c).strip().lower() for c in normalized.columns]
    normalized["sale_date"] = pd.to_datetime(normalized["sale_date"], errors="raise")
    normalized = normalized[normalized["sale_date"] >= MODEL_TRAIN_START].copy()
    if normalized.empty:
        raise ValueError(f"train has no rows on or after {MODEL_TRAIN_START.date()}")

    hours = tuple(range(open_hour, close_hour))
    weather_interp = interpolate_weather(weather) if weather is not None else None
    frame = build_frame(normalized, weather_interp, hours=hours)
    weights = make_sample_weights(frame)
    model = train_model(frame, weights)

    future_calendar = build_future_calendar(forecast_start, forecast_end, hours=hours)
    forecast = predict_recursive(model, normalized, future_calendar, weather_interp)

    forecast["sale_date"] = pd.to_datetime(forecast["sale_date"]).dt.date
    return forecast[["sale_date", "sale_hour", "guests_count"]]
