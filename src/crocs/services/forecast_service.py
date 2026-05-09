from __future__ import annotations

import pandas as pd

from crocs.exceptions import ForecastError


def run_forecast(train: pd.DataFrame) -> pd.DataFrame:
    if train is None or train.empty:
        raise ForecastError("train пуст")
    raise NotImplementedError("прогноз guests_count → колонки sale_date, sale_hour, guests_count")
