from __future__ import annotations

from datetime import date

import pandas as pd

from crocs.config import FORECAST_END, FORECAST_START, RESTAURANT_CLOSE_HOUR, RESTAURANT_OPEN_HOUR
from crocs.ml.lightgbm_pipeline import run_lightgbm_forecast


def run_forecast(
    train: pd.DataFrame,
    *,
    forecast_start: date | None = None,
    forecast_end: date | None = None,
    open_hour: int | None = None,
    close_hour: int | None = None,
    weather: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Прогноз гостей по часам (LightGBM + рекурсивное обновление лагов)."""
    return run_lightgbm_forecast(
        train,
        forecast_start=forecast_start if forecast_start is not None else FORECAST_START,
        forecast_end=forecast_end if forecast_end is not None else FORECAST_END,
        open_hour=open_hour if open_hour is not None else RESTAURANT_OPEN_HOUR,
        close_hour=close_hour if close_hour is not None else RESTAURANT_CLOSE_HOUR,
        weather=weather,
    )
