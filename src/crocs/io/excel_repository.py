from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)
from crocs.exceptions import DataValidationError


def _write_xlsx(df: pd.DataFrame, path: Path, columns: tuple[str, ...], label: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    missing = set(columns) - set(df.columns)
    if missing:
        raise ValueError(f"{label}: missing columns {sorted(missing)}")
    df[list(columns)].to_excel(path, index=False, engine="openpyxl")


def write_forecast_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, FORECAST_COLUMNS, "forecast")


def write_labor_demand_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, LABOR_DEMAND_COLUMNS, "labor_demand")


def write_schedule_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, SCHEDULE_COLUMNS, "schedule")


def write_coverage_report_xlsx(df: pd.DataFrame, path: Path) -> None:
    _write_xlsx(df, path, COVERAGE_REPORT_COLUMNS, "coverage_report")


def load_forecast_guests_xlsx(
    path: Path,
    *,
    start: date,
    end: date,
    open_hour: int,
    close_hour: int,
) -> pd.DataFrame:
    """
    Читает готовый почасовой прогноз гостей (sale_date, sale_hour, guests_count),
    оставляет только окно [start, end] и часы ресторана [open_hour, close_hour).
    """
    if close_hour <= open_hour:
        raise DataValidationError("forecast: close_hour должен быть больше open_hour")

    if not path.is_file():
        raise DataValidationError(
            f"guests_source=file: нет файла прогноза {path.resolve()}. "
            "Положите forecast.xlsx в forecast_input_dir.",
        )

    raw = pd.read_excel(path, engine="openpyxl")
    raw.columns = [str(c).strip().lower() for c in raw.columns]
    need = set(FORECAST_COLUMNS)
    if not need.issubset(raw.columns):
        raise DataValidationError(
            f"{path}: нужны колонки {sorted(need)}; в файле: {sorted(raw.columns)}",
        )

    work = raw[list(FORECAST_COLUMNS)].copy()
    work["sale_date"] = pd.to_datetime(work["sale_date"], errors="coerce")
    work = work.dropna(subset=["sale_date"])
    work["sale_hour"] = pd.to_numeric(work["sale_hour"], errors="coerce")
    work["guests_count"] = pd.to_numeric(work["guests_count"], errors="coerce")
    work = work.dropna(subset=["sale_hour", "guests_count"])

    ts_start = pd.Timestamp(start).normalize()
    ts_end = pd.Timestamp(end).normalize()
    mask_date = (work["sale_date"].dt.normalize() >= ts_start) & (
        work["sale_date"].dt.normalize() <= ts_end
    )
    hours_ok = set(range(int(open_hour), int(close_hour)))
    mask_hour = work["sale_hour"].astype(int).isin(hours_ok)
    work = work.loc[mask_date & mask_hour].copy()

    work["sale_hour"] = work["sale_hour"].astype(int)
    work["guests_count"] = work["guests_count"].clip(lower=0).round().astype(int)
    work = work.drop_duplicates(subset=["sale_date", "sale_hour"], keep="last")
    work = work.sort_values(["sale_date", "sale_hour"]).reset_index(drop=True)
    work["sale_date"] = work["sale_date"].dt.date

    if work.empty:
        raise DataValidationError(
            f"{path}: после фильтрации по датам {start}…{end} и часам {open_hour}…{close_hour - 1} "
            "не осталось ни одной строки. Проверьте конфиг forecast и содержимое файла.",
        )

    return work
