from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.schemas import FORECAST_COLUMNS, SCHEDULE_COLUMNS


def write_forecast_xlsx(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = set(FORECAST_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"forecast: не хватает колонок: {sorted(missing)}")
    df[list(FORECAST_COLUMNS)].to_excel(path, index=False)


def write_schedule_xlsx(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = set(SCHEDULE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"schedule: не хватает колонок: {sorted(missing)}")
    df[list(SCHEDULE_COLUMNS)].to_excel(path, index=False)
