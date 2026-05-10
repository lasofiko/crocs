from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FORECAST_COLUMNS = ("sale_date", "sale_hour", "guests_count")
LABOR_DEMAND_COLUMNS = ("ds", "sale_hour", "station_key", "required_employees")
SCHEDULE_COLUMNS = ("ds", "station_key", "employee_id", "starttime", "finishtime")
COVERAGE_REPORT_COLUMNS = ("ds", "station_key", "employee_id", "issue_type", "details")


@dataclass
class RawDataBundle:
    train: pd.DataFrame | None
    reqlabor: pd.DataFrame | None
    sched: pd.DataFrame | None
    station_priorities: pd.DataFrame | None
    shifts: pd.DataFrame | None
    staff_limits: pd.DataFrame | None


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
    max_extra_coverage: int = 2
    min_employees_per_station: int = 2
    restaurant_open_hour: int = 7
    restaurant_close_hour: int = 23
    solver_time_limit_seconds: float | None = None
