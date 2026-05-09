from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

FORECAST_COLUMNS = ("sale_date", "sale_hour", "guests_count")
SCHEDULE_COLUMNS = ("ds", "station_key", "employee_id", "starttime", "finishtime")


@dataclass
class RawDataBundle:
    train: Optional[pd.DataFrame]
    reqlabor: Optional[pd.DataFrame]
    sched: Optional[pd.DataFrame]
    station_priorities: Optional[pd.DataFrame]
    shifts: Optional[pd.DataFrame]
    staff_limits: Optional[pd.DataFrame]


@dataclass
class PipelineResult:
    forecast: pd.DataFrame
    schedule: pd.DataFrame
    warnings: list[str]


@dataclass
class SchedulingInputs:
    hourly_demand: pd.DataFrame
    sched: pd.DataFrame
    station_priorities: pd.DataFrame
    shifts: pd.DataFrame
    staff_limits: pd.DataFrame
