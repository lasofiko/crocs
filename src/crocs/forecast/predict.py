from __future__ import annotations

import pandas as pd

from crocs.exceptions import ForecastError


def run_forecast(train: pd.DataFrame) -> pd.DataFrame:
    """
    Прогноз guests_count по часам на целевую неделю.
    Ожидаемые колонки train — по вашему train.csv (задайте в features/model).
    """
    if train is None or train.empty:
        raise ForecastError("train.csv пуст или не загружен")
    raise NotImplementedError(
        "Реализуйте модель прогноза (baseline → CatBoost/LightGBM) и верните "
        "DataFrame с колонками sale_date, sale_hour, guests_count"
    )
