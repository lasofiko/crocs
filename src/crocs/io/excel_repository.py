from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.domain.models import FORECAST_COLUMNS, SCHEDULE_COLUMNS


def write_forecast_xlsx(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    miss = set(FORECAST_COLUMNS) - set(df.columns)
    if miss:
        raise ValueError(f"forecast: нет колонок {sorted(miss)}")
    df[list(FORECAST_COLUMNS)].to_excel(path, index=False)


def write_schedule_xlsx(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    miss = set(SCHEDULE_COLUMNS) - set(df.columns)
    if miss:
        raise ValueError(f"schedule: нет колонок {sorted(miss)}")
    df[list(SCHEDULE_COLUMNS)].to_excel(path, index=False)
