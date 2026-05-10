from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.minor_shift_limits import compute_staff_caps


def _nid(x: object) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, (float, int)) and float(x) == int(float(x)):
        return str(int(float(x)))
    return str(x).strip()


def _clock_hours(val: object) -> float:
    if pd.isna(val):
        return float("nan")
    if isinstance(val, bool):
        return float("nan")
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "hour") and hasattr(val, "minute"):
        return (
            float(val.hour)
            + float(val.minute) / 60.0
            + float(getattr(val, "second", 0)) / 3600.0
        )
    s = str(val).strip()
    if ":" in s:
        parts = s.split(":")
        h = float(parts[0])
        m = float(parts[1]) if len(parts) > 1 else 0.0
        sec = float(parts[2]) if len(parts) > 2 else 0.0
        return h + m / 60.0 + sec / 3600.0
    num = pd.to_numeric(s, errors="coerce")
    if pd.notna(num):
        return float(num)
    return float("nan")


@dataclass(frozen=True)
class _ShiftOption:
    emp_key: str
    emp_display: Any
    day_idx: int
    ds: Any
    station: str
    start_h: int
    duration: int
    shift_prio: int
    station_penalty: int

    def covers(self, hour: int) -> bool:
        return self.start_h <= hour < self.start_h + self.duration


def _parse_shifts(shifts: pd.DataFrame) -> list[tuple[int, int]]:
    sh = shifts.copy()
    sh.columns = [str(c).strip().lower() for c in sh.columns]
    dur_col = None
    prio_col = None
    for c in sh.columns:
        if c in ("shift_duration", "duration_hours", "hours", "shift_hours", "duration"):
            dur_col = c
        if c in ("shift_priority", "priority", "prio", "tier"):
            prio_col = c
    if dur_col is None:
        return [(8, 1)]
    rows: list[tuple[int, int]] = []
    for _, row in sh.iterrows():
        raw_d = row[dur_col]
        hrs = float(pd.to_numeric(raw_d, errors="coerce"))
        if pd.isna(hrs):
            continue
        d_int = round(hrs)
        if d_int <= 0:
            continue
        pr = 99
        if prio_col is not None:
            p = pd.to_numeric(row[prio_col], errors="coerce")
            if pd.notna(p):
                pr = int(p)
        rows.append((d_int, pr))
    if not rows:
        return [(8, 1)]
    rows.sort(key=lambda t: (t[1], t[0]))
    out: list[tuple[int, int]] = []
    seen: set[int] = set()
    for d_int, pr in rows:
        if d_int not in seen:
            seen.add(d_int)
            out.append((d_int, pr))
    return out


def _station_penalties(
    station_priorities: pd.DataFrame,
    emp_keys: list[str],
    stations: list[str],
) -> dict[tuple[str, str], int]:
    sp = station_priorities.copy()
    sp.columns = [str(c).strip().lower() for c in sp.columns]
    pen: dict[tuple[str, str], int] = {}
    ecols = ("employee_id", "staff_id", "emp_id")
    scol = None
    ecol = None
    pcol = None
    for c in sp.columns:
        if c in ("station_key", "station", "key"):
            scol = c
        if c in ecols:
            ecol = c
        if c in ("priority", "prio", "rank", "station_priority", "tier"):
            pcol = c
    default_station_only: dict[str, int] = {}
    if scol and pcol and ecol is None:
        for _, row in sp.iterrows():
            st = str(row[scol]).strip()
            p = pd.to_numeric(row[pcol], errors="coerce")
            if pd.notna(p):
                default_station_only[st] = int(p)
        for ek in emp_keys:
            for st in stations:
                pen[(ek, st)] = default_station_only.get(st, 5)
        return pen

    if scol and pcol and ecol:
        for _, row in sp.iterrows():
            ek = _nid(row[ecol])
            st = str(row[scol]).strip()
            p = pd.to_numeric(row[pcol], errors="coerce")
            if pd.isna(ek) or not ek or pd.isna(p):
                continue
            pen[(ek, st)] = int(p)
        for ek in emp_keys:
            for st in stations:
                pen.setdefault((ek, st), 5)
        return pen

    for ek in emp_keys:
        for st in stations:
            pen[(ek, st)] = 5
    return pen


def _sched_windows(sched: pd.DataFrame) -> dict[tuple[str, int], tuple[float, float]]:
    s = sched.copy()
    s.columns = [str(c).strip().lower() for c in s.columns]
    ecol = dcol = stcol = ftcol = None
    for c in s.columns:
        if c in ("employee_id", "staff_id", "emp_id"):
            ecol = c
        if c in ("day", "weekday", "day_of_week", "dow"):
            dcol = c
        if c in ("starttime", "start", "from"):
            stcol = c
        if c in ("finishtime", "finish", "end", "to"):
            ftcol = c
    if not all([ecol, dcol, stcol, ftcol]):
        raise ScheduleError("sched: need employee_id, day, starttime, finishtime")

    merged: dict[tuple[str, int], list[float]] = defaultdict(lambda: [1e9, -1e9])
    for _, row in s.iterrows():
        ek = _nid(row[ecol])
        if not ek:
            continue
        wd = int(float(pd.to_numeric(row[dcol], errors="coerce")))
        lo = _clock_hours(row[stcol])
        hi = _clock_hours(row[ftcol])
        if pd.isna(lo) or pd.isna(hi):
            continue
        key = (ek, wd)
        cur = merged[key]
        cur[0] = min(cur[0], lo)
        cur[1] = max(cur[1], hi)
    out: dict[tuple[str, int], tuple[float, float]] = {}
    for key, v in merged.items():
        lo, hi = v
        if hi > lo:
            out[key] = (lo, hi)
    return out


def _demand_grid(
    hourly_demand: pd.DataFrame,
) -> tuple[list[Any], list[int], list[str], dict[tuple[int, int, str], int], dict[int, Any]]:
    h = hourly_demand.copy()
    h.columns = [str(c).strip().lower() for c in h.columns]
    need = ("ds", "sale_hour", "station_key", "required_employees")
    if any(c not in h for c in need):
        raise ScheduleError("hourly_demand: need ds, sale_hour, station_key, required_employees")

    h["ds"] = pd.to_datetime(h["ds"], errors="coerce").dt.normalize()
    h = h.dropna(subset=["ds"])
    h["sale_hour"] = pd.to_numeric(h["sale_hour"], errors="coerce").astype("Int64")
    h["required_employees"] = pd.to_numeric(h["required_employees"], errors="coerce").fillna(0)
    h["station_key"] = h["station_key"].astype(str)

    agg = h.groupby(["ds", "sale_hour", "station_key"], as_index=False)["required_employees"].max()
    days = sorted(agg["ds"].unique().tolist())
    if len(days) != 7:
        msg = f"hourly_demand: expected 7 days, got {len(days)}"
        raise ScheduleError(msg)

    hours_set: set[int] = set()
    for x in agg["sale_hour"].dropna().astype(int).tolist():
        hours_set.add(int(x))
    hours = sorted(hours_set)

    stations = sorted(agg["station_key"].unique().tolist())
    demand: dict[tuple[int, int, str], int] = {}
    for _, row in agg.iterrows():
        d = row["ds"]
        day_idx = days.index(d)
        hour = int(row["sale_hour"])
        st = str(row["station_key"])
        req_val = float(row["required_employees"])
        demand[(day_idx, hour, st)] = max(0, round(req_val))

    for di in range(len(days)):
        for hour in hours:
            for st in stations:
                demand.setdefault((di, hour, st), 0)

    day_ts = {i: days[i] for i in range(len(days))}
    return days, hours, stations, demand, day_ts


def solve_schedule_cp_sat(inputs: SchedulingInputs) -> pd.DataFrame:
    open_h = inputs.restaurant_open_hour
    close_h = inputs.restaurant_close_hour
    rest_end_exc = close_h + 1
    max_extra = inputs.max_extra_coverage

    days, hours, stations, demand_raw, day_ts = _demand_grid(inputs.hourly_demand)
    demand = demand_raw
    floor_n = inputs.min_employees_per_station
    if floor_n > 0:
        demand = {k: max(int(v), floor_n) for k, v in demand.items()}
    shift_pairs = _parse_shifts(inputs.shifts)
    week_cap, shift_cap = compute_staff_caps(inputs.staff_limits, pd.Timestamp(days[0]))
    windows = _sched_windows(inputs.sched)

    sched_df = inputs.sched.copy()
    sched_df.columns = [str(c).strip().lower() for c in sched_df.columns]
    ecol = next(c for c in sched_df.columns if c in ("employee_id", "staff_id", "emp_id"))
    roster_keys = sorted({_nid(x) for x in sched_df[ecol].dropna()}, key=lambda x: x)
    roster_display: dict[str, Any] = {}
    for _, row in sched_df.iterrows():
        ek = _nid(row[ecol])
        if ek and ek not in roster_display:
            roster_display[ek] = row[ecol]

    station_pen = _station_penalties(inputs.station_priorities, roster_keys, stations)

    options: list[_ShiftOption] = []
    for ek in roster_keys:
        emp_obj = roster_display[ek]
        smax = shift_cap.get(ek, 24.0)
        for day_idx in range(len(days)):
            ts = day_ts[day_idx]
            wd = int(pd.Timestamp(ts).dayofweek + 1)
            win = windows.get((ek, wd))
            if win is None:
                continue
            win_lo, win_hi = win
            for st in stations:
                spen = station_pen.get((ek, st), 5)
                for dur, spr in shift_pairs:
                    if dur > smax + 1e-6:
                        continue
                    for start_h in range(open_h, rest_end_exc):
                        end_exc = start_h + dur
                        if end_exc > rest_end_exc:
                            break
                        if start_h + 1e-9 < win_lo or end_exc > win_hi + 1e-9:
                            continue
                        options.append(
                            _ShiftOption(
                                emp_key=ek,
                                emp_display=emp_obj,
                                day_idx=day_idx,
                                ds=ts,
                                station=st,
                                start_h=start_h,
                                duration=dur,
                                shift_prio=spr,
                                station_penalty=spen,
                            )
                        )

    if not options:
        raise ScheduleError(
            "no feasible shift templates (check sched, shifts, staff_limits)",
        )

    roster_with_any = {o.emp_key for o in options}
    missing = [roster_display[k] for k in roster_keys if k not in roster_with_any]
    if missing:
        raise ScheduleError(
            "employees have no feasible shift on the horizon: "
            + ", ".join(str(x) for x in missing[:10]),
        )

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x_{i}") for i in range(len(options))]

    by_emp_day: dict[tuple[str, int], list[int]] = defaultdict(list)
    by_emp: dict[str, list[int]] = defaultdict(list)
    coverage_idxs: dict[tuple[int, int, str], list[int]] = defaultdict(list)

    for i, opt in enumerate(options):
        by_emp_day[(opt.emp_key, opt.day_idx)].append(i)
        by_emp[opt.emp_key].append(i)
        for hour in hours:
            if opt.covers(hour):
                coverage_idxs[(opt.day_idx, hour, opt.station)].append(i)

    for _ek_d, idxs in by_emp_day.items():
        model.Add(sum(x[j] for j in idxs) <= 1)

    for key, req in demand.items():
        di, hour, st = key
        idxs = coverage_idxs.get((di, hour, st), [])
        if req == 0:
            if idxs:
                model.Add(sum(x[j] for j in idxs) <= max_extra)
            continue
        if not idxs:
            ds_label = pd.Timestamp(day_ts[di]).strftime("%Y-%m-%d (%A)")
            hint = (
                "В sched.csv колонка day: понедельник=1 … воскресенье=7. "
                "Окно starttime..finishtime должно допускать смену из shifts.csv на этот час; "
                f"проверьте shift_limit. Дата={ds_label}."
            )
            raise ScheduleError(
                f"Нет ни одной допустимой смены под спрос: день index={di}, час={hour}, "
                f"станция={st}, нужно={req}. {hint}",
            )
        model.Add(sum(x[j] for j in idxs) >= req)
        model.Add(sum(x[j] for j in idxs) <= req + max_extra)

    for ek in roster_keys:
        idxs = by_emp[ek]
        wc = week_cap.get(ek)
        if wc is not None and idxs:
            cap_w = max(0, math.ceil(float(wc) - 1e-9))
            model.Add(sum(x[j] * int(options[j].duration) for j in idxs) <= cap_w)
        idxs_emp = [j for j in range(len(options)) if options[j].emp_key == ek]
        max_sh = max(1, int(inputs.max_shifts_per_employee_week))
        if idxs_emp:
            model.Add(sum(x[j] for j in idxs_emp) <= max_sh)
            model.Add(sum(x[j] for j in idxs_emp) >= 1)

    obj_terms: list[cp_model.LinearExpr] = []
    for i, opt in enumerate(options):
        coeff = opt.shift_prio * 1000 + opt.station_penalty * 100
        obj_terms.append(x[i] * int(coeff))

    model.Minimize(sum(obj_terms))

    solver = cp_model.CpSolver()
    if inputs.solver_time_limit_seconds is not None:
        solver.parameters.max_time_in_seconds = float(inputs.solver_time_limit_seconds)
    solver.parameters.num_search_workers = 8

    status = solver.Solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise ScheduleError(
            "CP-SAT found no feasible schedule (check staffing, demand, sched windows). "
            f"status={solver.StatusName(status)}",
        )

    rows_out: list[dict[str, Any]] = []
    for i, opt in enumerate(options):
        if solver.Value(x[i]) != 1:
            continue
        end_h = float(opt.start_h + opt.duration)
        rows_out.append(
            {
                "ds": pd.Timestamp(opt.ds).strftime("%Y-%m-%d"),
                "station_key": opt.station,
                "employee_id": opt.emp_display,
                "starttime": float(opt.start_h),
                "finishtime": end_h,
            }
        )

    if not rows_out:
        raise ScheduleError("solver returned an empty schedule")

    out = pd.DataFrame(rows_out)
    return out
