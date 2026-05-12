from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FORECAST_COLUMNS = ("sale_date", "sale_hour", "guests_count")
LABOR_DEMAND_COLUMNS = ("ds", "sale_hour", "station_key", "required_employees", "assigned_employees")
SCHEDULE_COLUMNS = ("ds", "station_key", "employee_id", "starttime", "finishtime")
COVERAGE_REPORT_COLUMNS = ("ds", "station_key", "employee_id", "issue_type", "details")


@dataclass
class RawDataBundle:
    train: pd.DataFrame | None
    weather: pd.DataFrame | None
    reqlabor: pd.DataFrame | None
    sched: pd.DataFrame | None
    staff_limits: pd.DataFrame | None
    station_priorities: pd.DataFrame | None
    shifts: pd.DataFrame | None


@dataclass
class PipelineResult:
    forecast: pd.DataFrame
    warnings: list[str]
    schedule: pd.DataFrame | None = None
    labor_demand: pd.DataFrame | None = None


@dataclass
class SchedulingInputs:
    hourly_demand: pd.DataFrame
    sched: pd.DataFrame
    station_priorities: pd.DataFrame
    shifts: pd.DataFrame
    staff_limits: pd.DataFrame
    max_extra_coverage: int = 2
    min_employees_per_station: int = 1
    min_employees_relaxed_sale_hours: tuple[int, ...] = ()
    max_shifts_per_employee_week: int = 5
    require_one_shift_per_sched_employee: bool = True
    restaurant_open_hour: int = 7
    restaurant_close_hour: int = 23
    solver_time_limit_seconds: float | None = None
    cp_sat_stop_after_first_solution: bool = False
    lns_enabled: bool = True
    lns_iterations: int = 14
    lns_repair_seconds: float | None = None
    lns_destroy_days_min: int = 1
    lns_destroy_days_max: int = 2
    lns_staff_destroy_fraction: float = 0.1
    lns_seed: int | None = None
