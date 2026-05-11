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
from crocs.services.staffing_counts import staff_counts_per_slot


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


def write_schedule_staffing_by_hour_xlsx(
    schedule_df: pd.DataFrame,
    labor_demand_df: pd.DataFrame,
    *,
    open_hour: int,
    close_hour: int,
    path: Path,
) -> None:
    """
    Книга Excel: один лист на каждый календарный день из labor_demand_df.

    На листе строки — часы ресторана [open_hour, close_hour), колонки — станции,
    значения — сколько человек одновременно назначено на станцию в этот час.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if close_hour <= open_hour:
        raise ValueError("close_hour must be greater than open_hour")

    ld = labor_demand_df.copy()
    if ld.empty:
        pd.DataFrame({"msg": ["нет labor_demand — нечего сводить"]}).to_excel(
            path, index=False, engine="openpyxl"
        )
        return

    ld.columns = [str(c).strip().lower() for c in ld.columns]
    ld["ds"] = pd.to_datetime(ld["ds"], errors="coerce").dt.normalize()
    ld = ld.dropna(subset=["ds"])
    stations = sorted(ld["station_key"].dropna().astype(str).unique().tolist())
    days = sorted(ld["ds"].unique())
    hour_rows = list(range(int(open_hour), int(close_hour)))

    long_df = staff_counts_per_slot(schedule_df, int(open_hour), int(close_hour))
    if not long_df.empty:
        long_df = long_df.copy()
        long_df["ds"] = pd.to_datetime(long_df["ds"], errors="coerce").dt.normalize()
        long_df["station_key"] = long_df["station_key"].astype(str)

    def table_for_day(day_ts: pd.Timestamp) -> pd.DataFrame:
        sub = long_df[long_df["ds"] == day_ts] if not long_df.empty else long_df
        if not stations:
            return pd.DataFrame({"sale_hour": hour_rows})
        if sub.empty:
            return pd.DataFrame({"sale_hour": hour_rows, **{st: 0 for st in stations}})
        pt = sub.pivot_table(
            index="sale_hour",
            columns="station_key",
            values="assigned",
            aggfunc="sum",
            fill_value=0,
        )
        for st in stations:
            if st not in pt.columns:
                pt[st] = 0
        pt = pt[stations]
        wide = pt.reindex(hour_rows, fill_value=0)
        out = wide.reset_index()
        if str(out.columns[0]) != "sale_hour":
            out = out.rename(columns={out.columns[0]: "sale_hour"})
        return out

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for day_ts in days:
            stem = pd.Timestamp(day_ts).strftime("%Y-%m-%d")
            sheet = stem[:31]
            table_for_day(pd.Timestamp(day_ts).normalize()).to_excel(
                writer, sheet_name=sheet, index=False
            )


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
    Читает готовый почасовой прогноз гостей (как из ML: sale_date, sale_hour, guests_count),
    оставляет только окно [start, end] и часы ресторана [open_hour, close_hour).
    """
    if close_hour <= open_hour:
        raise DataValidationError("forecast: close_hour должен быть больше open_hour")

    if not path.is_file():
        raise DataValidationError(
            f"guests_source=file: нет файла прогноза {path.resolve()}. "
            "Положите forecast.xlsx (из ML) в schedule_input_dir.",
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
