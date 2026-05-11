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
    # На каждой станции в каждом почасовом слоте горизонта — не меньше стольки человек одновременно
    # (после порога из reqlabor/прогноза значение required_employees поднимается до этого минимума).
    min_employees_per_station: int = 2
    # В эти sale_hour нижняя граница — 1 человек на станцию (см. configs scheduling.*).
    min_employees_relaxed_sale_hours: tuple[int, ...] = ()
    # За плановую неделю (горизонт): каждый из sched — минимум одна смена, не больше max_shifts_per_employee_week.
    max_shifts_per_employee_week: int = 5
    restaurant_open_hour: int = 7
    # Час закрытия; почасовой спрос использует sale_hour ∈ [open, close).
    restaurant_close_hour: int = 23
    solver_time_limit_seconds: float | None = None
