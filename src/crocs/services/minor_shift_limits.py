from __future__ import annotations

from datetime import date

import pandas as pd


def _nid(x: object) -> str:
    if pd.isna(x):
        return ""
    if isinstance(x, (float, int)) and float(x) == int(float(x)):
        return str(int(float(x)))
    return str(x).strip()


def age_completed_on_reference(reference: pd.Timestamp, birth: pd.Timestamp) -> int:
    """Полных лет на дату reference (календарная проверка дня рождения)."""
    r = reference.date() if isinstance(reference, pd.Timestamp) else reference
    b = birth.date() if isinstance(birth, pd.Timestamp) else birth
    if not isinstance(r, date):
        r = pd.Timestamp(reference).date()
    if not isinstance(b, date):
        b = pd.Timestamp(birth).date()
    years = r.year - b.year
    if (r.month, r.day) < (b.month, b.day):
        years -= 1
    return years


def minor_max_shift_hours(age: int | None) -> float | None:

    if age is None:
        return None
    caps: list[float] = []
    if 14 <= age <= 15:
        caps.append(4.0)
    if 15 <= age <= 16:
        caps.append(5.0)
    if 16 <= age <= 18:
        caps.append(7.0)
    if not caps:
        return None
    return min(caps)


def effective_shift_cap_hours(file_shift_limit: float | None, age: int | None) -> float:
    """Итоговый максимум длины смены: минимум из таблицы и возрастного потолка."""
    minor = minor_max_shift_hours(age)
    caps: list[float] = []
    if file_shift_limit is not None:
        caps.append(float(file_shift_limit))
    if minor is not None:
        caps.append(minor)
    if not caps:
        return 24.0
    return min(caps)


def parse_employee_age_by_id(
    staff_limits: pd.DataFrame,
    reference_day: pd.Timestamp,
) -> dict[str, int | None]:
    """employee_key -> возраст в полных годах на reference_day (или None)."""
    lim = staff_limits.copy()
    lim.columns = [str(c).strip().lower() for c in lim.columns]
    eid_col = None
    for c in lim.columns:
        if c in ("employee_id", "staff_id", "emp_id"):
            eid_col = c
            break
    if eid_col is None:
        return {}

    age_col = None
    for c in lim.columns:
        if c in ("age", "age_years", "возраст"):
            age_col = c
            break

    birth_col = None
    for c in lim.columns:
        if c in ("birth_date", "birthdate", "date_of_birth", "дата_рождения"):
            birth_col = c
            break

    ref = pd.Timestamp(reference_day).normalize()
    out: dict[str, int | None] = {}

    def _nid(x: object) -> str:
        if pd.isna(x):
            return ""
        if isinstance(x, (float, int)) and float(x) == int(float(x)):
            return str(int(float(x)))
        return str(x).strip()

    for _, row in lim.iterrows():
        k = _nid(row[eid_col])
        if not k:
            continue
        ag: int | None = None
        if age_col is not None and pd.notna(row.get(age_col)):
            try:
                ag = int(float(row[age_col]))
            except (TypeError, ValueError):
                ag = None
        elif birth_col is not None and pd.notna(row.get(birth_col)):
            birth = pd.to_datetime(row[birth_col], errors="coerce")
            if pd.notna(birth):
                ag = age_completed_on_reference(ref, pd.Timestamp(birth))
        out[k] = ag
    return out


def compute_staff_caps(
    staff_limits: pd.DataFrame,
    reference_day: pd.Timestamp,
) -> tuple[dict[str, float], dict[str, float]]:

    lim = staff_limits.copy()
    lim.columns = [str(c).strip().lower() for c in lim.columns]
    eid = None
    for c in lim.columns:
        if c in ("employee_id", "staff_id", "emp_id"):
            eid = c
            break
    week_col = None
    shift_col = None
    for c in lim.columns:
        if c in (
            "worktime_limit",
            "max_week_hours",
            "weekly_hours_max",
            "hours_week_max",
            "max_hours_week",
            "week_hours",
        ):
            week_col = c
        if c in (
            "shift_limit",
            "max_shift_hours",
            "shift_hours_max",
            "max_daily_hours",
            "shift_max_hours",
        ):
            shift_col = c
    week: dict[str, float] = {}
    shift: dict[str, float] = {}
    if eid is None:
        return week, shift

    ages = parse_employee_age_by_id(staff_limits, reference_day)

    for _, row in lim.iterrows():
        k = _nid(row[eid])
        if not k:
            continue
        if week_col is not None and pd.notna(row.get(week_col)):
            wv = float(row[week_col])
            week[k] = min(week.get(k, wv), wv)
        file_sl = None
        if shift_col is not None and pd.notna(row.get(shift_col)):
            file_sl = float(row[shift_col])
        age = ages.get(k)
        eff = effective_shift_cap_hours(file_sl, age)
        shift[k] = min(shift.get(k, eff), eff)

    return week, shift
