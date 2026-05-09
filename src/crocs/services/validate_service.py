from __future__ import annotations

from typing import Iterable

import pandas as pd

_ID = ("employee_id", "staff_id", "emp_id")
_WEEK_CAP = (
    "worktime_limit",
    "max_week_hours",
    "weekly_hours_max",
    "hours_week_max",
    "max_hours_week",
    "week_hours",
)
_SHIFT_CAP = (
    "shift_limit",
    "max_shift_hours",
    "shift_hours_max",
    "max_daily_hours",
    "shift_max_hours",
)
_WDAY = ("day", "weekday", "day_of_week", "dow")
_PRIO = ("shift_priority", "priority", "prio", "tier")
_DUR = ("shift_duration", "duration_hours", "hours", "shift_hours", "duration")


def _col(df: pd.DataFrame, aliases: Iterable[str]) -> str | None:
    m = {str(c).strip().lower(): c for c in df.columns}
    for a in aliases:
        if a.lower() in m:
            return m[a.lower()]
    return None


def _nid(x: object) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, (float, int)) and float(x) == int(float(x)):
        return str(int(float(x)))
    return str(x).strip()


def _clock_hours(val: object) -> float:
    """Часы от начала дня: число 9 -> 9:00, строка '09:30' -> 9.5, time/timestamp из Excel."""
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


# Перевод в норм рабочее время и проверка на валидность данных
def validate_schedule(
    schedule: pd.DataFrame,
    staff_limits: pd.DataFrame,
    sched: pd.DataFrame,
    shifts: pd.DataFrame | None = None,
) -> list[str]:
    bad: list[str] = []

    if schedule is None or schedule.empty:
        return ["пустое расписание"]

    lc = {str(c).strip().lower(): c for c in schedule.columns}
    for req in ("ds", "employee_id", "starttime", "finishtime"):
        if req not in lc:
            return [f"в schedule нет колонки {req}"]

    s = schedule.rename(columns=lc).copy()
    ds = pd.to_datetime(s["ds"], errors="coerce")
    day = ds.dt.normalize()
    h0 = s["starttime"].map(_clock_hours)
    h1 = s["finishtime"].map(_clock_hours)
    t0 = pd.to_datetime(day, errors="coerce") + pd.to_timedelta(h0, unit="h")
    t1 = pd.to_datetime(day, errors="coerce") + pd.to_timedelta(h1, unit="h")
    overnight = t1 < t0
    t1 = t1.where(~overnight, t1 + pd.Timedelta(days=1))
    s["_dur_h"] = (t1 - t0).dt.total_seconds() / 3600.0
    if s["_dur_h"].isna().any() or (s["_dur_h"] <= 0).any():
        bad.append("некорректная длительность смены")

    s["_wd"] = ds.dt.dayofweek + 1

    # Лимиты по закону / рабочему дню: неделя и одна смена (staff_limits), непонятно что делать если очнь много часов или стоит работа фулл дей
    eid_lim = _col(staff_limits, _ID)
    c_week = _col(staff_limits, _WEEK_CAP)
    c_shift = _col(staff_limits, _SHIFT_CAP)
    if eid_lim is None:
        bad.append("staff_limits: нет employee_id — проверка лимитов часов пропущена")
    elif not c_week and not c_shift:
        bad.append("staff_limits: нет колонок лимита недели/смены — проверка лимитов пропущена")
    else:
        sl = staff_limits.rename(columns=lambda x: str(x).strip().lower())
        lid = str(eid_lim).lower()
        sum_w = s.groupby("employee_id")["_dur_h"].sum()
        max_s = s.groupby("employee_id")["_dur_h"].max()
        cw = str(c_week).lower() if c_week else None
        cs = str(c_shift).lower() if c_shift else None
        for _, row in sl.iterrows():
            e = row.get(lid)
            if pd.isna(e):
                continue
            k = _nid(e)
            if cw and cw in row.index and pd.notna(row[cw]):
                cap = float(row[cw])
                keys = [x for x in sum_w.index if _nid(x) == k]
                if keys and float(sum_w[keys[0]]) > cap + 1e-6:
                    bad.append(f"часов за неделю больше лимита: сотрудник {e}, {float(sum_w[keys[0]]):.2f}ч > {cap}ч")
            if cs and cs in row.index and pd.notna(row[cs]):
                cap = float(row[cs])
                keys = [x for x in max_s.index if _nid(x) == k]
                if keys and float(max_s[keys[0]]) > cap + 1e-6:
                    bad.append(f"смена длиннее допустимой: сотрудник {e}, {float(max_s[keys[0]]):.2f}ч > {cap}ч")

    # Только дни недели 1–7; назначение только в разрешённые в sched дни и что делать если не хватает на день работников
    sid = _col(sched, _ID)
    swd = _col(sched, _WDAY)
    allowed: dict[str, set[int]] = {}
    roster: set[str] = set()
    if sid is None or swd is None:
        bad.append("sched: нет employee_id или weekday — проверка дней 1–7 пропущена")
    else:
        sf = sched.rename(columns=lambda x: str(x).strip().lower())
        ci, cw = str(sid).lower(), str(swd).lower()
        for _, row in sf.iterrows():
            e = row.get(ci)
            if pd.isna(e):
                continue
            roster.add(_nid(e))
            w = row.get(cw)
            if pd.isna(w):
                continue
            try:
                wi = int(w)
            except (TypeError, ValueError):
                bad.append(f"sched: weekday не целое (сотрудник {e})")
                continue
            if wi < 1 or wi > 7:
                bad.append(f"sched: weekday вне 1–7 (сотрудник {e}, weekday={w})")
                continue
            allowed.setdefault(_nid(e), set()).add(wi)

        for emp, g in s.groupby("employee_id"):
            k = _nid(emp)
            if k not in allowed:
                bad.append(f"сотрудник {emp} есть в расписании, но нет строк доступности в sched")
                continue
            for w in g["_wd"].dropna().astype(int).unique():
                if int(w) not in allowed[k]:
                    bad.append(f"сотрудник {emp}: работа в день недели {int(w)}, не разрешённом в sched")

        have = {_nid(x) for x in s["employee_id"].dropna().unique()}
        for k in roster:
            if k not in have:
                bad.append(f"у сотрудника из sched (id={k}) нет ни одной смены — нужен минимум один рабочий день")

    # Рабочие дни минимум 2 выходных и минимум 1 рабочий день, пока не понятно что делать при нарушении
    h = pd.date_range(ds.min().normalize(), ds.max().normalize(), freq="D")
    if len(h) != 7:
        bad.append(f"ожидается ровно 7 календарных дней, получилось {len(h)}")

    for emp, g in s.groupby("employee_id"):
        days_work = set(pd.to_datetime(g["ds"]).dt.normalize().unique())
        if len(days_work) < 1:
            bad.append(f"сотрудник {emp}: нет ни одного рабочего дня")
        off = len(set(h) - days_work)
        if off < 2:
            bad.append(f"сотрудник {emp}: меньше двух выходных в неделе (выходных {off})")

    # Длительность каждой смены соответствует таблице приоритетов 1–4. в зависимости от ответа на наш вопрос про кол-во времени решу что делать с приоритетами но пока оно надо какбудто
    if shifts is None or shifts.empty:
        bad.append("shifts пуст — проверка приоритетов 1–4 пропущена")
    else:
        cp = _col(shifts, _PRIO)
        cd = _col(shifts, _DUR)
        if cp is None or cd is None:
            bad.append("shifts: нужны колонки priority и длительность")
        else:
            sh = shifts.rename(columns=lambda x: str(x).strip().lower())
            pl, dl = str(cp).lower(), str(cd).lower()
            ok_hours: set[float] = set()
            for _, row in sh.iterrows():
                try:
                    pr = int(row[pl])
                    hrs = float(row[dl])
                except (TypeError, ValueError):
                    continue
                if 1 <= pr <= 4:
                    ok_hours.add(round(hrs, 6))
            if not ok_hours:
                bad.append("shifts: нет ни одной строки с priority 1–4 и часами")
            else:
                eps = 1e-2
                for _, row in s.iterrows():
                    d = float(row["_dur_h"])
                    if not any(abs(d - x) <= eps for x in ok_hours):
                        bad.append(
                            f"длительность смены {d:.2f}ч не из допустимых по shifts (приоритеты могут быть 1–4): "
                            f"{sorted(ok_hours)}"
                        )
                        break

    return bad
