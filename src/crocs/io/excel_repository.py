from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)


def _write_xlsx(df: pd.DataFrame, path: Path, columns: tuple[str, ...], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{label}: missing columns {sorted(missing)}")
    # openpyxl уже тянется для read_excel; xlsxwriter опционален
    df[list(columns)].to_excel(path, index=False, engine="openpyxl")


def write_forecast_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, FORECAST_COLUMNS, "forecast")


def write_labor_demand_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, LABOR_DEMAND_COLUMNS, "labor_demand")


def write_schedule_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, SCHEDULE_COLUMNS, "schedule")


def write_coverage_report_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, COVERAGE_REPORT_COLUMNS, "coverage_report")
