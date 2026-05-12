from __future__ import annotations

from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field

from crocs.domain.models import COVERAGE_REPORT_COLUMNS
from crocs.viz.report_figures import staff_counts_per_slot


def enrich_labor_demand_with_assigned(
    labor_demand_df: pd.DataFrame,
    schedule_df: pd.DataFrame | None,
    *,
    open_hour: int,
    close_hour: int,
) -> pd.DataFrame:
    """Добавляет столбец assigned_employees: сколько человек на станции в слоте по факту смен."""
    out = labor_demand_df.copy()
    out.columns = [str(c).strip().lower() for c in out.columns]
    out["ds"] = pd.to_datetime(out["ds"], errors="coerce").dt.normalize()
    if "assigned_employees" in out.columns:
        out = out.drop(columns=["assigned_employees"])
    assigned_df = staff_counts_per_slot(
        schedule_df if schedule_df is not None else pd.DataFrame(),
        open_hour,
        close_hour,
    )
    if not assigned_df.empty:
        assigned_df = assigned_df.rename(columns={"assigned": "assigned_employees"})
        assigned_df["ds"] = pd.to_datetime(assigned_df["ds"], errors="coerce").dt.normalize()
        out = out.merge(assigned_df, on=["ds", "sale_hour", "station_key"], how="left")
    else:
        out["assigned_employees"] = 0
    out["assigned_employees"] = pd.to_numeric(out["assigned_employees"], errors="coerce").fillna(0).astype(int)
    return out

_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _shift_covers_hour(start: float, finish: float, hour: int) -> bool:
    return start <= hour < finish


def _employee_ids_for_slot(
    schedule_df: pd.DataFrame,
    *,
    ds: pd.Timestamp,
    sale_hour: int,
    station_key: str,
) -> list[str]:
    if schedule_df is None or schedule_df.empty:
        return []
    s = schedule_df.copy()
    s.columns = [str(c).strip().lower() for c in s.columns]
    s["ds"] = pd.to_datetime(s["ds"], errors="coerce").dt.normalize()
    day = pd.Timestamp(ds).normalize()
    out: list[str] = []
    for _, r in s.iterrows():
        if pd.isna(r["ds"]) or pd.Timestamp(r["ds"]).normalize() != day:
            continue
        if str(r["station_key"]) != str(station_key):
            continue
        t0 = float(r["starttime"])
        t1 = float(r["finishtime"])
        if _shift_covers_hour(t0, t1, sale_hour):
            out.append(str(r["employee_id"]))
    return sorted(set(out), key=lambda x: (len(x), x))


def _coverage_status(required: int, assigned: int) -> Literal["ok", "short", "vacant", "surplus"]:
    if required <= 0:
        return "ok" if assigned == 0 else "surplus"
    if assigned <= 0:
        return "vacant"
    if assigned < required:
        return "short"
    if assigned > required:
        return "surplus"
    return "ok"


class StaffingGridRow(BaseModel):
    """Одна строка сетки: дата × час × станция."""

    date: str = Field(description="Дата YYYY-MM-DD")
    weekday: int = Field(ge=1, le=7, description="Пн=1 … Вс=7")
    weekday_name_ru: str
    sale_hour: int
    station_key: str
    guests_forecast_total: int = Field(
        description="Прогноз гостей в зале в этот час (общий по ресторану, тот же для всех станций в слоте).",
    )
    required_employees: int = Field(description="Целевая численность по нормативу (после min на станцию).")
    assigned_employees: int = Field(description="Сколько человек назначено на станции в этот час по сменам.")
    employee_ids: list[str] = Field(default_factory=list)
    coverage_status: Literal["ok", "short", "vacant", "surplus"]
    coverage_gap: int = Field(description="assigned − required (отрицательно = нехватка).")


class StaffingGridResponse(BaseModel):
    rows: list[StaffingGridRow]
    warnings: list[str] = Field(default_factory=list)


def build_staffing_grid(
    forecast_df: pd.DataFrame,
    labor_demand_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    *,
    open_hour: int,
    close_hour: int,
    warnings: list[str] | None = None,
) -> StaffingGridResponse:
    """
    Сводная таблица для фронта: прогноз гостей, требуемые и назначенные люди по станциям, список сотрудников.
    """
    warn = list(warnings or [])
    if labor_demand_df is None or labor_demand_df.empty:
        return StaffingGridResponse(rows=[], warnings=warn + ["labor_demand пуст — нечего отдавать."])

    d = labor_demand_df.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]
    d["ds"] = pd.to_datetime(d["ds"], errors="coerce").dt.normalize()
    if "assigned_employees" in d.columns:
        d = d.drop(columns=["assigned_employees"])

    fc = forecast_df.copy()
    fc.columns = [str(c).strip().lower() for c in fc.columns]
    fc["ds"] = pd.to_datetime(fc["sale_date"], errors="coerce").dt.normalize()
    guests_slot = fc.groupby(["ds", "sale_hour"], as_index=False)["guests_count"].max()
    guests_slot["guests_forecast_total"] = (
        pd.to_numeric(guests_slot["guests_count"], errors="coerce").fillna(0).round().astype(int)
    )

    merged = d.merge(guests_slot[["ds", "sale_hour", "guests_forecast_total"]], on=["ds", "sale_hour"], how="left")
    merged["guests_forecast_total"] = merged["guests_forecast_total"].fillna(0).astype(int)

    assigned_df = staff_counts_per_slot(schedule_df, open_hour, close_hour)
    if not assigned_df.empty:
        assigned_df["ds"] = pd.to_datetime(assigned_df["ds"], errors="coerce").dt.normalize()
        merged = merged.merge(
            assigned_df,
            on=["ds", "sale_hour", "station_key"],
            how="left",
        )
    else:
        merged["assigned"] = 0

    merged["assigned"] = pd.to_numeric(merged["assigned"], errors="coerce").fillna(0).astype(int)
    merged["required_employees"] = pd.to_numeric(merged["required_employees"], errors="coerce").fillna(0).astype(
        int
    )

    rows_out: list[StaffingGridRow] = []
    for _, row in merged.iterrows():
        ds = pd.Timestamp(row["ds"]).normalize()
        hour = int(row["sale_hour"])
        st = str(row["station_key"])
        req = int(row["required_employees"])
        asn = int(row["assigned"])
        guests = int(row["guests_forecast_total"])
        wd0 = int(ds.weekday())  # пн=0
        weekday = wd0 + 1
        weekday_name = _WEEKDAY_RU[wd0]
        emps = _employee_ids_for_slot(schedule_df, ds=ds, sale_hour=hour, station_key=st)
        status = _coverage_status(req, asn)
        gap = asn - req
        rows_out.append(
            StaffingGridRow(
                date=ds.strftime("%Y-%m-%d"),
                weekday=weekday,
                weekday_name_ru=weekday_name,
                sale_hour=hour,
                station_key=st,
                guests_forecast_total=guests,
                required_employees=req,
                assigned_employees=asn,
                employee_ids=emps,
                coverage_status=status,
                coverage_gap=gap,
            )
        )

    rows_out.sort(key=lambda r: (r.date, r.sale_hour, r.station_key))
    return StaffingGridResponse(rows=rows_out, warnings=warn)


def staffing_grid_to_records(response: StaffingGridResponse) -> list[dict[str, Any]]:
    """Плоский JSON-сериализуемый список словарей."""
    return [r.model_dump() for r in response.rows]


def coverage_report_dataframe(grid: StaffingGridResponse) -> pd.DataFrame:
    """Строки для coverage_report.xlsx: только слоты, где покрытие не «ok»."""
    rows: list[dict[str, object]] = []
    for r in grid.rows:
        if r.coverage_status == "ok":
            continue
        emps = ",".join(r.employee_ids)[:500]
        rows.append(
            {
                "ds": pd.Timestamp(r.date).normalize(),
                "station_key": r.station_key,
                "employee_id": emps,
                "issue_type": r.coverage_status,
                "details": (
                    f"required={r.required_employees} assigned={r.assigned_employees} "
                    f"guests_slot={r.guests_forecast_total}"
                ),
            }
        )
    return pd.DataFrame(rows, columns=list(COVERAGE_REPORT_COLUMNS))
