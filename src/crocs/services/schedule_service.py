from __future__ import annotations

import pandas as pd

from crocs.config import FORECAST_END, FORECAST_START, RESTAURANT_OPEN_HOUR
from crocs.domain.models import SchedulingInputs


def _nid(x: object) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, (float, int)) and float(x) == int(float(x)):
        return str(int(float(x)))
    return str(x).strip()


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    """
    Заглушка расписания: по одной смене в день (до 5 дней в неделе) на сотрудника,
    станция по кругу из demand, длительность смены из shifts (допустимая по окну sched).
    Потом заменить на CP-SAT.
    """
    h = inputs.hourly_demand
    sched = inputs.sched
    shifts = inputs.shifts
    staff_limits = inputs.staff_limits

    sh = shifts.copy()
    sh.columns = [str(c).strip().lower() for c in sh.columns]
    durs: list[float] = []
    if "shift_duration" in sh.columns:
        if "shift_priority" in sh.columns:
            for pr in sorted(pd.to_numeric(sh["shift_priority"], errors="coerce").dropna().unique()):
                part = sh.loc[sh["shift_priority"] == pr, "shift_duration"]
                durs.extend(pd.to_numeric(part, errors="coerce").dropna().astype(float).tolist())
        else:
            durs = pd.to_numeric(sh["shift_duration"], errors="coerce").dropna().astype(float).tolist()
    if not durs:
        durs = [8.0]
    durs = sorted(set(durs))

    sched_df = sched.copy()
    sched_df.columns = [str(c).strip().lower() for c in sched_df.columns]
    for col in ("employee_id", "day", "starttime", "finishtime"):
        if col not in sched_df.columns:
            raise ValueError(f"sched: нет колонки {col}")

    lim_df = staff_limits.copy()
    lim_df.columns = [str(c).strip().lower() for c in lim_df.columns]
    cap_shift: dict[str, float] = {}
    if "employee_id" in lim_df.columns and "shift_limit" in lim_df.columns:
        for _, r in lim_df.iterrows():
            cap_shift[_nid(r["employee_id"])] = float(r["shift_limit"])

    stations: list[str] = []
    if not h.empty and "station_key" in h.columns:
        stations = sorted(h["station_key"].dropna().astype(str).unique().tolist())
    if not stations:
        stations = ["K"]

    horizon = pd.date_range(FORECAST_START, FORECAST_END, freq="D")
    emps = sorted(sched_df["employee_id"].dropna().unique(), key=lambda x: str(x))

    rows_out: list[dict] = []
    st_ix = 0
    for emp in emps:
        ek = _nid(emp)
        emp_rows = sched_df[sched_df["employee_id"].map(_nid) == ek]
        allowed = {int(float(x)) for x in emp_rows["day"].dropna().unique()}
        max_shift = cap_shift.get(ek, max(durs))

        cand_days = [d for d in horizon if int(d.dayofweek) + 1 in allowed]
        work_days = cand_days[:5]

        for d in work_days:
            wd = int(d.dayofweek) + 1
            dr = emp_rows[pd.to_numeric(emp_rows["day"], errors="coerce").astype(int) == wd]
            if dr.empty:
                continue
            r0 = dr.iloc[0]
            st_h = int(float(r0["starttime"]))
            ft_h = int(float(r0["finishtime"]))
            window = max(0.0, float(ft_h - st_h))

            chosen = None
            for cand in sorted(durs):
                if cand <= min(window, max_shift) + 1e-9:
                    chosen = cand
            if chosen is None:
                chosen = min(durs)

            end_h = float(st_h) + float(chosen)
            if end_h > float(ft_h):
                end_h = float(ft_h)
            station = stations[st_ix % len(stations)]
            st_ix += 1
            rows_out.append(
                {
                    "ds": d.strftime("%Y-%m-%d"),
                    "station_key": station,
                    "employee_id": emp,
                    "starttime": st_h,
                    "finishtime": end_h,
                }
            )

    if not rows_out:
        rows_out.append(
            {
                "ds": FORECAST_START.strftime("%Y-%m-%d"),
                "station_key": stations[0],
                "employee_id": emps[0] if len(emps) else 0,
                "starttime": RESTAURANT_OPEN_HOUR,
                "finishtime": RESTAURANT_OPEN_HOUR + float(min(durs)),
            }
        )

    return pd.DataFrame(rows_out)
