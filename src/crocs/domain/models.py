from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FORECAST_COLUMNS = ("sale_date", "sale_hour", "guests_count")


@dataclass
class RawDataBundle:
    train: pd.DataFrame | None
    weather: pd.DataFrame | None
    reqlabor: pd.DataFrame | None
    sched: pd.DataFrame | None
    station_priorities: pd.DataFrame | None
    shifts: pd.DataFrame | None
    staff_limits: pd.DataFrame | None


@dataclass
class PipelineResult:
    forecast: pd.DataFrame
    warnings: list[str]
