from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

from crocs.domain.models import SCHEDULE_COLUMNS
from crocs.services.validate_service import _clock_hours


def _weekday_js(ts: pd.Timestamp) -> int:
    """Понедельник = 1 … воскресенье = 7 (как `Date.getDay()` на фронте с воскресеньем = 7)."""
    return int(ts.dayofweek + 1)


def _iter_open_hours(ds: object, starttime: object, finishtime: object) -> list[tuple[str, int, int]]:
    """Слоты [час, час+1), пересекающиеся со сменой; (date_iso, weekday_js, hour)."""
    day0 = pd.Timestamp(ds).normalize()
    h0 = _clock_hours(starttime)
    h1 = _clock_hours(finishtime)
    if h0 != h0 or h1 != h1:  # NaN
        return []
    t0 = day0 + pd.to_timedelta(h0, unit="h")
    t1 = day0 + pd.to_timedelta(h1, unit="h")
    if t1 <= t0:
        t1 = t1 + pd.Timedelta(days=1)

    cur = t0.floor("h")
    out: list[tuple[str, int, int]] = []
    while cur < t1:
        out.append((cur.strftime("%Y-%m-%d"), _weekday_js(cur), int(cur.hour)))
        cur = cur + pd.Timedelta(hours=1)
    return out


def _load_forecast_guests(forecast_path: Path) -> dict[tuple[str, int], int]:
    if not forecast_path.is_file():
        return {}
    df = pd.read_excel(forecast_path, engine="openpyxl")
    cols = {str(c).strip().lower(): c for c in df.columns}
    need = ("sale_date", "sale_hour", "guests_count")
    if not all(k in cols for k in need):
        return {}
    guests: dict[tuple[str, int], int] = {}
    for _, row in df.iterrows():
        d = pd.Timestamp(row[cols["sale_date"]]).strftime("%Y-%m-%d")
        h = int(pd.to_numeric(row[cols["sale_hour"]], errors="coerce"))
        if h != h:
            continue
        g = int(pd.to_numeric(row[cols["guests_count"]], errors="coerce") or 0)
        key = (d, h)
        guests[key] = max(guests.get(key, 0), g)
    return guests


def build_schedule_animation_items(artifacts_dir: Path) -> list[dict[str, Any]]:
    """
    Разворачивает смены schedule.xlsx в почасовые строки для UI (одна строка на день-час-станцию).
    Число гостей подмешивается из forecast.xlsx при наличии.
    """
    schedule_path = artifacts_dir / "schedule.xlsx"
    if not schedule_path.is_file():
        return []

    df = pd.read_excel(schedule_path, engine="openpyxl")
    lc = {str(c).strip().lower(): c for c in df.columns}
    missing = [c for c in SCHEDULE_COLUMNS if c not in lc]
    if missing:
        return []

    guests_map = _load_forecast_guests(artifacts_dir / "forecast.xlsx")

    # (date, weekday, hour, station) -> employee ids
    acc: dict[tuple[str, int, int, str], list[str]] = defaultdict(list)

    for _, row in df.iterrows():
        ds = row[lc["ds"]]
        station = str(row[lc["station_key"]]).strip()
        eid_raw = row[lc["employee_id"]]
        if pd.isna(eid_raw):
            continue
        eid = str(int(eid_raw)) if isinstance(eid_raw, float) and float(eid_raw).is_integer() else str(eid_raw).strip()
        if not station or not eid:
            continue

        for date_str, wd, hour in _iter_open_hours(ds, row[lc["starttime"]], row[lc["finishtime"]]):
            acc[(date_str, wd, hour, station)].append(eid)

    items: list[dict[str, Any]] = []
    for (date_str, wd, hour, station), eids in sorted(acc.items()):
        uniq = list(dict.fromkeys(eids))
        n = len(uniq)
        gc = guests_map.get((date_str, hour), 0)
        items.append(
            {
                "date": date_str,
                "day": wd,
                "hour": hour,
                "station": station,
                "employeeIds": uniq,
                "expectedPeopleCount": max(n, 1),
                "atStationCount": n,
                "expectationIndicator": "ok",
                "visitorsCount": gc,
            }
        )
    return items


def schedule_excel_path(artifacts_dir: Path) -> Path:
    return artifacts_dir / "schedule.xlsx"
