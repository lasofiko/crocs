from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from crocs.config import RESTAURANT_CLOSE_HOUR, RESTAURANT_OPEN_HOUR
from crocs.ml.baseline import build_future_calendar
from crocs.ml.features import MODEL_TRAIN_START, prepare_hourly_series

HOURS_DEFAULT = tuple(range(RESTAURANT_OPEN_HOUR, RESTAURANT_CLOSE_HOUR))
TARGET_COLUMN = "guests_count"

BASE_FEATURES = ["sale_hour", "day_of_week", "month"]
WEATHER_FEATURES = ["temp_c", "precipitation_mm"]
HOLIDAY_FEATURES = [
    "is_ru_holiday_non_working",
    "holiday_new_year",
    "holiday_defender_day",
    "holiday_womens_day",
    "holiday_may_day",
    "holiday_victory_day",
    "holiday_russia_day",
    "holiday_unity_day",
]
LAG_DAYS = [1, 7, 14]
ROLLING_MEAN_WINDOWS = [7, 30]
ROLLING_STD_WINDOWS = [7]
LAG_FEATURES = [f"lag_{lag}d" for lag in LAG_DAYS]
ROLLING_FEATURES = [
    *[f"rolling_mean_{window}d" for window in ROLLING_MEAN_WINDOWS],
    *[f"rolling_std_{window}d" for window in ROLLING_STD_WINDOWS],
]
DIFF_FEATURES = [
    "diff_lag_1d_7d",
    "diff_lag_7d_14d",
    "diff_lag_1d_14d",
    "diff_lag_1d_roll_7d",
    "diff_roll_7d_30d",
]
CYCLIC_FEATURES = ["hour_sin", "hour_cos", "dow_sin", "dow_cos", "month_sin", "month_cos"]
TABULAR = [
    *BASE_FEATURES,
    *WEATHER_FEATURES,
    *HOLIDAY_FEATURES,
    *LAG_FEATURES,
    *ROLLING_FEATURES,
    *DIFF_FEATURES,
    *CYCLIC_FEATURES,
]
CATS: list[str] = []

MODEL_PARAMS: dict[str, Any] = {
    "objective": "mae",
    "n_estimators": 350,
    "learning_rate": 0.04,
    "max_depth": 4,
    "num_leaves": 15,
    "min_child_samples": 25,
    "subsample": 0.9,
    "colsample_bytree": 0.9,
    "random_state": 42,
    "n_jobs": -1,
    "verbose": -1,
}

HOLIDAY_PERIODS = {
    "new_year": [
        ("2022-01-01", "2022-01-09"),
        ("2023-01-01", "2023-01-08"),
        ("2024-01-01", "2024-01-08"),
        ("2025-01-01", "2025-01-08"),
        ("2026-01-01", "2026-01-11"),
    ],
    "defender_day": [
        ("2022-02-23", "2022-02-23"),
        ("2023-02-23", "2023-02-26"),
        ("2024-02-23", "2024-02-25"),
        ("2025-02-22", "2025-02-24"),
        ("2026-02-21", "2026-02-23"),
    ],
    "womens_day": [
        ("2022-03-06", "2022-03-08"),
        ("2023-03-08", "2023-03-08"),
        ("2024-03-08", "2024-03-10"),
        ("2025-03-08", "2025-03-09"),
        ("2026-03-07", "2026-03-09"),
    ],
    "may_day": [
        ("2022-04-30", "2022-05-03"),
        ("2023-04-29", "2023-05-01"),
        ("2024-04-28", "2024-05-01"),
        ("2025-05-01", "2025-05-04"),
        ("2026-05-01", "2026-05-03"),
    ],
    "victory_day": [
        ("2022-05-07", "2022-05-10"),
        ("2023-05-06", "2023-05-09"),
        ("2024-05-09", "2024-05-12"),
        ("2025-05-08", "2025-05-11"),
        ("2026-05-09", "2026-05-11"),
    ],
    "russia_day": [
        ("2022-06-11", "2022-06-13"),
        ("2023-06-10", "2023-06-12"),
        ("2024-06-12", "2024-06-12"),
        ("2025-06-12", "2025-06-15"),
        ("2026-06-12", "2026-06-14"),
    ],
    "unity_day": [
        ("2022-11-04", "2022-11-06"),
        ("2023-11-04", "2023-11-06"),
        ("2024-11-03", "2024-11-04"),
        ("2025-11-02", "2025-11-04"),
        ("2026-11-04", "2026-11-04"),
    ],
}


def _holiday_by_date() -> dict[date, str]:
    result: dict[date, str] = {}
    for holiday_name, periods in HOLIDAY_PERIODS.items():
        for start_text, end_text in periods:
            current = date.fromisoformat(start_text)
            end = date.fromisoformat(end_text)
            while current <= end:
                result[current] = holiday_name
                current += timedelta(days=1)
    return result


def upcoming_break_days(d: pd.Timestamp, max_horizon: int = 14) -> int:
    holiday_by_date = _holiday_by_date()
    current = pd.Timestamp(d).date()
    count = 0
    for delta in range(1, max_horizon + 1):
        probe = current + timedelta(days=delta)
        if probe.weekday() >= 5 or probe in holiday_by_date:
            count += 1
        else:
            break
    return count


def interpolate_weather(weather_raw: pd.DataFrame | None) -> pd.DataFrame | None:
    if weather_raw is None or weather_raw.empty:
        return None

    work = weather_raw.copy()
    work["sale_date"] = pd.to_datetime(work["sale_date"], errors="raise")
    work["sale_hour"] = work["sale_hour"].astype(int)
    keep = ["sale_date", "sale_hour", *[col for col in WEATHER_FEATURES if col in work.columns]]
    work = work[keep]

    all_dates = pd.date_range(work["sale_date"].min(), work["sale_date"].max(), freq="D")
    full_idx = pd.MultiIndex.from_product(
        [all_dates, range(0, 24)],
        names=["sale_date", "sale_hour"],
    )
    work = work.set_index(["sale_date", "sale_hour"]).reindex(full_idx).reset_index()
    cols = [col for col in WEATHER_FEATURES if col in work.columns]
    work[cols] = work.groupby("sale_date")[cols].ffill(limit=3)
    work[cols] = work.groupby("sale_date")[cols].bfill(limit=3)
    return work


def add_time_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    dates = pd.to_datetime(out["sale_date"], errors="raise")
    out["sale_hour"] = out["sale_hour"].astype(int)
    out["day_of_week"] = dates.dt.dayofweek.astype(int)
    out["month"] = dates.dt.month.astype(int)
    return out


def add_weather_features_simple(
    frame: pd.DataFrame,
    weather_interp: pd.DataFrame | None,
) -> pd.DataFrame:
    out = frame.copy()
    if weather_interp is None or weather_interp.empty:
        for col in WEATHER_FEATURES:
            out[col] = np.nan
        return out

    weather = weather_interp[["sale_date", "sale_hour", *WEATHER_FEATURES]].copy()
    weather["sale_date"] = pd.to_datetime(weather["sale_date"], errors="raise")
    weather["sale_hour"] = weather["sale_hour"].astype(int)
    out["sale_date"] = pd.to_datetime(out["sale_date"], errors="raise")
    out["sale_hour"] = out["sale_hour"].astype(int)
    return out.merge(weather, on=["sale_date", "sale_hour"], how="left")


def add_ru_holiday_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    dates = pd.to_datetime(out["sale_date"], errors="raise").dt.date
    holiday_by_date = _holiday_by_date()
    out["is_ru_holiday_non_working"] = dates.isin(holiday_by_date).astype(int)
    for holiday_name in HOLIDAY_PERIODS:
        out[f"holiday_{holiday_name}"] = dates.map(
            lambda current, name=holiday_name: int(holiday_by_date.get(current) == name)
        )
    return out


def add_lag_features_simple(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["sale_hour", "sale_date"]).copy()
    grouped = out.groupby("sale_hour", group_keys=False)[TARGET_COLUMN]
    for lag in LAG_DAYS:
        out[f"lag_{lag}d"] = grouped.shift(lag)
    return out.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)


def add_rolling_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.sort_values(["sale_hour", "sale_date"]).copy()
    grouped = out.groupby("sale_hour", group_keys=False)[TARGET_COLUMN]
    for window in ROLLING_MEAN_WINDOWS:
        out[f"rolling_mean_{window}d"] = grouped.transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=max(2, w // 2)).mean()
        )
    for window in ROLLING_STD_WINDOWS:
        out[f"rolling_std_{window}d"] = grouped.transform(
            lambda s, w=window: s.shift(1).rolling(w, min_periods=max(2, w // 2)).std()
        )
    return out.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)


def add_diff_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    candidates = [
        ("diff_lag_1d_7d", "lag_1d", "lag_7d"),
        ("diff_lag_7d_14d", "lag_7d", "lag_14d"),
        ("diff_lag_1d_14d", "lag_1d", "lag_14d"),
        ("diff_lag_1d_roll_7d", "lag_1d", "rolling_mean_7d"),
        ("diff_roll_7d_30d", "rolling_mean_7d", "rolling_mean_30d"),
    ]
    for name, left, right in candidates:
        if left in out.columns and right in out.columns:
            out[name] = out[left] - out[right]
    return out


def add_cyclic_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["hour_sin"] = np.sin(2 * np.pi * out["sale_hour"] / 24)
    out["hour_cos"] = np.cos(2 * np.pi * out["sale_hour"] / 24)
    out["dow_sin"] = np.sin(2 * np.pi * out["day_of_week"] / 7)
    out["dow_cos"] = np.cos(2 * np.pi * out["day_of_week"] / 7)
    out["month_sin"] = np.sin(2 * np.pi * out["month"] / 12)
    out["month_cos"] = np.cos(2 * np.pi * out["month"] / 12)
    return out


def build_frame(
    train: pd.DataFrame,
    weather_interp: pd.DataFrame | None,
    hours: tuple[int, ...] = HOURS_DEFAULT,
) -> pd.DataFrame:
    series = prepare_hourly_series(train, hours=hours)
    featured = build_feature_frame(series, weather_interp)
    required = [TARGET_COLUMN, *LAG_FEATURES]
    return featured.dropna(subset=required).reset_index(drop=True)


def build_feature_frame(frame: pd.DataFrame, weather_interp: pd.DataFrame | None) -> pd.DataFrame:
    featured = add_time_features(frame)
    featured = add_weather_features_simple(featured, weather_interp)
    featured = add_ru_holiday_features(featured)
    featured = add_lag_features_simple(featured)
    featured = add_rolling_features(featured)
    featured = add_diff_features(featured)
    return add_cyclic_features(featured)


def make_sample_weights(frame: pd.DataFrame) -> None:
    return None


def feature_fill_values(train_frame: pd.DataFrame) -> dict[str, float]:
    values: dict[str, float] = {}
    for col in TABULAR:
        series = pd.to_numeric(train_frame[col], errors="coerce")
        fill = series.median()
        values[col] = float(fill) if pd.notna(fill) else -9999.0
    return values


def prep_features(frame: pd.DataFrame, fill_values: dict[str, float] | None = None) -> pd.DataFrame:
    if fill_values is None:
        fill_values = {col: -9999.0 for col in TABULAR}
    feat = frame[TABULAR].copy()
    for col in TABULAR:
        feat[col] = pd.to_numeric(feat[col], errors="coerce").fillna(fill_values[col])
    return feat


prep_for_cat = prep_features


def train_model(
    train_frame: pd.DataFrame,
    weights: np.ndarray | None = None,
    seed: int = 42,
) -> LGBMRegressor:
    params = {**MODEL_PARAMS, "random_state": seed}
    model = LGBMRegressor(**params)
    fill_values = feature_fill_values(train_frame)
    model.fit(
        prep_features(train_frame, fill_values),
        train_frame[TARGET_COLUMN].astype(float),
        sample_weight=weights,
    )
    model._crocs_fill_values = fill_values
    return model


def predict_recursive(
    model: LGBMRegressor,
    history: pd.DataFrame,
    calendar: pd.DataFrame,
    weather_interp: pd.DataFrame | None,
) -> pd.DataFrame:
    history_frame = history[["sale_date", "sale_hour", TARGET_COLUMN]].copy()
    history_frame["sale_date"] = pd.to_datetime(history_frame["sale_date"])
    cal = calendar[["sale_date", "sale_hour"]].copy()
    cal["sale_date"] = pd.to_datetime(cal["sale_date"])
    fill_values = getattr(model, "_crocs_fill_values", None)

    predictions: list[pd.DataFrame] = []
    for sale_date in sorted(cal["sale_date"].unique()):
        current = cal[cal["sale_date"] == sale_date].copy()
        current_aug = current.copy()
        current_aug[TARGET_COLUMN] = np.nan
        combined = pd.concat([history_frame, current_aug], ignore_index=True)

        featured = build_feature_frame(combined, weather_interp)
        today = featured[featured["sale_date"] == sale_date].copy()
        pred = model.predict(prep_features(today, fill_values))

        out = current.copy()
        out[TARGET_COLUMN] = np.clip(np.round(pred), 0, None).astype(int)
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
    weather_interp = interpolate_weather(weather)
    frame = build_frame(normalized, weather_interp, hours=hours)
    model = train_model(frame, make_sample_weights(frame))

    future_calendar = build_future_calendar(forecast_start, forecast_end, hours=hours)
    forecast = predict_recursive(model, normalized, future_calendar, weather_interp)

    forecast["sale_date"] = pd.to_datetime(forecast["sale_date"]).dt.date
    return forecast[["sale_date", "sale_hour", TARGET_COLUMN]]
