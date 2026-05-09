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
    labor_demand: pd.DataFrame
    schedule: pd.DataFrame
    coverage_report: pd.DataFrame


@dataclass
class SchedulingInputs:
    hourly_demand: pd.DataFrame
    sched: pd.DataFrame
    station_priorities: pd.DataFrame
    shifts: pd.DataFrame
    staff_limits: pd.DataFrame
