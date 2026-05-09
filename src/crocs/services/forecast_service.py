from __future__ import annotations

import pandas as pd

from crocs.config import FORECAST_END, FORECAST_START, RESTAURANT_CLOSE_HOUR, RESTAURANT_OPEN_HOUR
from crocs.exceptions import ForecastError


def run_forecast(train: pd.DataFrame) -> pd.DataFrame:
    """
    Заглушка прогноза: средние гости по (день_недели, час) из train,
    применяются к горизонту FORECAST_START..FORECAST_END и окну ресторана.
    Потом заменить на LGBM / CatBoost и т.д.
    """
    if train.empty:
        raise ForecastError("train is empty")

    t = train.copy()
    t.columns = [str(c).strip().lower() for c in t.columns]
    need = ("sale_date", "sale_hour", "guests_count")
    for col in need:
        if col not in t.columns:
            raise ForecastError(f"train: нет колонки {col}")

    t["_d"] = pd.to_datetime(t["sale_date"], errors="coerce")
    if t["_d"].isna().any():
        raise ForecastError("train: некорректные sale_date")

    t["_wd"] = t["_d"].dt.dayofweek + 1
    t["sale_hour"] = t["sale_hour"].astype(int)
    agg = t.groupby(["_wd", "sale_hour"], as_index=False)["guests_count"].mean()
    agg.columns = ["wd", "sale_hour", "g_mean"]
    fallback = float(t["guests_count"].median()) if t["guests_count"].notna().any() else 10.0

    rows: list[dict] = []
    for day in pd.date_range(FORECAST_START, FORECAST_END, freq="D"):
        wd = int(day.dayofweek) + 1
        for hour in range(RESTAURANT_OPEN_HOUR, RESTAURANT_CLOSE_HOUR + 1):
            m = agg[(agg["wd"] == wd) & (agg["sale_hour"] == hour)]
            g = float(m["g_mean"].iloc[0]) if len(m) else fallback
            rows.append(
                {
                    "sale_date": day.date(),
                    "sale_hour": hour,
                    "guests_count": max(0.0, g),
                }
            )

    return pd.DataFrame(rows)
