from __future__ import annotations

import pandas as pd

from crocs.exceptions import ForecastError


def run_forecast(train: pd.DataFrame) -> pd.DataFrame:
    if train.empty:
        raise ForecastError("train is empty")
    raise NotImplementedError("guest forecast -> sale_date, sale_hour, guests_count")
