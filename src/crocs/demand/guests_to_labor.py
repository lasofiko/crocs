from __future__ import annotations

import pandas as pd


def build_hourly_demand(
    forecast_guests: pd.DataFrame,
    reqlabor: pd.DataFrame,
) -> pd.DataFrame:
    """
    Перевод прогноза гостей в потребность по станциям: день × час × station_key → headcount.
    Логика берётся из reqlabor.csv (будни/выходные, тип меню и т.д.).
    """
    raise NotImplementedError(
        "Реализуйте расчёт потребности по reqlabor.csv для каждого часа и станции"
    )
