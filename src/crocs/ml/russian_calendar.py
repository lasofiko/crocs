from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

HOLIDAY_NAME_CODES = {
    "none": 0,
    "new_year": 1,
    "defender_day": 2,
    "womens_day": 3,
    "may_day": 4,
    "victory_day": 5,
    "russia_day": 6,
    "unity_day": 7,
}

FIXED_PUBLIC_HOLIDAYS = (
    (1, 1),
    (1, 2),
    (1, 3),
    (1, 4),
    (1, 5),
    (1, 6),
    (1, 7),
    (1, 8),
    (2, 23),
    (3, 8),
    (5, 1),
    (5, 9),
    (6, 12),
    (11, 4),
)

GENERIC_HOLIDAY_BLOCKS = (
    ("new_year", 1, 1, 8),
    ("defender_day", 2, 21, 23),
    ("womens_day", 3, 7, 9),
    ("may_day", 5, 1, 3),
    ("victory_day", 5, 9, 11),
    ("russia_day", 6, 12, 14),
    ("unity_day", 11, 4, 4),
)

OFFICIAL_2026_NON_WORKING_DAYS = {
    date(2026, 1, day) for day in range(1, 12)
} | {
    date(2026, 2, day) for day in range(21, 24)
} | {
    date(2026, 3, day) for day in range(7, 10)
} | {
    date(2026, 5, day) for day in range(1, 4)
} | {
    date(2026, 5, day) for day in range(9, 12)
} | {
    date(2026, 6, day) for day in range(12, 15)
} | {
    date(2026, 11, 4),
    date(2026, 12, 31),
}


def add_russian_calendar_features(df: pd.DataFrame, date_column: str = "sale_date") -> pd.DataFrame:
    """Add Russian public-holiday features for forecasting restaurant demand."""
    featured = df.copy()
    dates = pd.to_datetime(featured[date_column], errors="raise").dt.date

    years = range(min(dates).year - 1, max(dates).year + 2)
    fixed_holidays = _fixed_holidays_for_years(years)
    preholidays = {holiday - timedelta(days=1) for holiday in fixed_holidays}

    featured["is_ru_public_holiday"] = dates.isin(fixed_holidays).astype(int)
    featured["is_ru_preholiday"] = dates.isin(preholidays).astype(int)
    featured["is_ru_holiday_period"] = dates.map(_is_holiday_period).astype(int)
    featured["is_may_holiday_season"] = dates.map(_is_may_holiday_season).astype(int)
    featured["is_may_day_block"] = dates.map(lambda current: _in_block(current, "may_day")).astype(
        int
    )
    featured["is_victory_day_block"] = dates.map(
        lambda current: _in_block(current, "victory_day")
    ).astype(int)
    featured["is_ru_long_weekend"] = dates.map(_is_long_weekend).astype(int)
    featured["holiday_name_code"] = dates.map(_holiday_name_code).astype(int)
    featured["holiday_block_day_index"] = dates.map(_holiday_block_day_index).astype(int)
    featured["holiday_block_length"] = dates.map(_holiday_block_length).astype(int)
    featured["days_to_may_day"] = dates.map(lambda current: _days_to_month_day(current, 5, 1))
    featured["days_since_may_day"] = dates.map(
        lambda current: _days_since_month_day(current, 5, 1)
    )
    featured["days_to_victory_day"] = dates.map(lambda current: _days_to_month_day(current, 5, 9))
    featured["days_since_victory_day"] = dates.map(
        lambda current: _days_since_month_day(current, 5, 9)
    )
    featured["days_to_next_ru_holiday"] = dates.map(
        lambda current: _days_to_next(current, fixed_holidays)
    ).astype(int)
    featured["days_since_prev_ru_holiday"] = dates.map(
        lambda current: _days_since_previous(current, fixed_holidays)
    ).astype(int)
    return featured


def _fixed_holidays_for_years(years: range) -> set[date]:
    return {date(year, month, day) for year in years for month, day in FIXED_PUBLIC_HOLIDAYS}


def _is_holiday_period(current: date) -> bool:
    if current in OFFICIAL_2026_NON_WORKING_DAYS:
        return True
    return _holiday_block(current) is not None


def _is_may_holiday_season(current: date) -> bool:
    return (current.month == 5 and current.day <= 12) or (
        current.month == 4 and current.day >= 29
    )


def _holiday_block(current: date) -> tuple[str, date, date] | None:
    for name, month, start_day, end_day in GENERIC_HOLIDAY_BLOCKS:
        start = date(current.year, month, start_day)
        end = date(current.year, month, end_day)
        if start <= current <= end:
            return name, start, end
    return None


def _in_block(current: date, block_name: str) -> bool:
    block = _holiday_block(current)
    return block is not None and block[0] == block_name


def _is_long_weekend(current: date) -> bool:
    block = _holiday_block(current)
    if block is None:
        return False
    return (block[2] - block[1]).days + 1 >= 3


def _holiday_name_code(current: date) -> int:
    block = _holiday_block(current)
    if block is None:
        return HOLIDAY_NAME_CODES["none"]
    return HOLIDAY_NAME_CODES[block[0]]


def _holiday_block_day_index(current: date) -> int:
    block = _holiday_block(current)
    if block is None:
        return 0
    return (current - block[1]).days + 1


def _holiday_block_length(current: date) -> int:
    block = _holiday_block(current)
    if block is None:
        return 0
    return (block[2] - block[1]).days + 1


def _days_to_month_day(current: date, month: int, day: int) -> int:
    target = date(current.year, month, day)
    if current > target:
        target = date(current.year + 1, month, day)
    return (target - current).days


def _days_since_month_day(current: date, month: int, day: int) -> int:
    target = date(current.year, month, day)
    if current < target:
        target = date(current.year - 1, month, day)
    return (current - target).days


def _days_to_next(current: date, holidays: set[date]) -> int:
    future = [holiday for holiday in holidays if holiday >= current]
    if not future:
        return 366
    return min((holiday - current).days for holiday in future)


def _days_since_previous(current: date, holidays: set[date]) -> int:
    previous = [holiday for holiday in holidays if holiday <= current]
    if not previous:
        return 366
    return min((current - holiday).days for holiday in previous)
