"""Почасовой подсчёт назначенных сотрудников по станциям (без зависимостей от matplotlib)."""

from __future__ import annotations

import pandas as pd


def shift_covers_hour(start: float, finish: float, hour: int) -> bool:
    return start <= hour < finish


def staff_counts_per_slot(
    schedule_df: pd.DataFrame, open_h: int, close_h: int
) -> pd.DataFrame:
    """Число назначенных сотрудников по (ds, sale_hour, station_key)."""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])

    s = schedule_df.copy()
    s.columns = [str(c).strip().lower() for c in s.columns]
    s["ds"] = pd.to_datetime(s["ds"], errors="coerce").dt.normalize()
    rows: list[dict] = []
    for _, r in s.iterrows():
        if pd.isna(r["ds"]):
            continue
        st = str(r["station_key"])
        t0 = float(r["starttime"])
        t1 = float(r["finishtime"])
        for h in range(open_h, close_h):
            if shift_covers_hour(t0, t1, h):
                rows.append({"ds": r["ds"], "sale_hour": h, "station_key": st})
    if not rows:
        return pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])
    return (
        pd.DataFrame(rows)
        .groupby(["ds", "sale_hour", "station_key"])
        .size()
        .reset_index(name="assigned")
    )
