from __future__ import annotations

from typing import Any

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.services.minor_shift_limits import compute_staff_caps
from crocs.services.schedule_cp_sat import (
    _demand_grid,
    _nid,
    _parse_shifts,
    _sched_windows,
)

_WEEKDAY_RU = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


def _geometric_can_cover_hour(
    ek: str,
    day_idx: int,
    hour: int,
    *,
    day_ts: dict[int, Any],
    windows: dict[tuple[str, int], tuple[float, float]],
    shift_pairs: list[tuple[int, int]],
    shift_cap: dict[str, float],
    open_h: int,
    close_h: int,
) -> bool:
    ts = day_ts[day_idx]
    wd = int(pd.Timestamp(ts).dayofweek + 1)
    win = windows.get((ek, wd))
    if win is None:
        return False
    win_lo, win_hi = win
    smax = shift_cap.get(ek, 24.0)
    rest_end_exc = close_h + 1
    for dur, _ in shift_pairs:
        if dur > smax + 1e-6:
            continue
        for start_h in range(open_h, rest_end_exc):
            end_exc = start_h + dur
            if end_exc > rest_end_exc:
                break
            if start_h + 1e-9 < win_lo or end_exc > win_hi + 1e-9:
                continue
            if start_h <= hour < end_exc:
                return True
    return False


def staffing_shortfall_hints(
    inputs: SchedulingInputs,
    *,
    max_slots: int = 12,
    max_donors_per_slot: int = 8,
) -> list[str]:
    """
    Если на слот не хватает людей по геометрии sched/shifts/лимитам смены,
    подсказать сотрудников, у которых в другие дни уже есть подходящее окно
    на этот же час (можно расширить sched.csv по образцу).
    """
    open_h = inputs.restaurant_open_hour
    close_h = inputs.restaurant_close_hour
    floor_n = inputs.min_employees_per_station

    days, _hours, _stations, demand_raw, day_ts = _demand_grid(inputs.hourly_demand)
    demand = demand_raw
    if floor_n > 0:
        demand = {k: max(int(v), floor_n) for k, v in demand.items()}

    shift_pairs = _parse_shifts(inputs.shifts)
    _, shift_cap = compute_staff_caps(inputs.staff_limits, pd.Timestamp(days[0]))
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

    hints: list[str] = []
    n_days = len(days)

    for key in sorted(demand.keys(), key=lambda k: (k[0], k[1], k[2])):
        di, hour, st = key
        need = int(demand[key])
        if need <= 0:
            continue

        covering: list[str] = []
        for ek in roster_keys:
            if _geometric_can_cover_hour(
                ek,
                di,
                hour,
                day_ts=day_ts,
                windows=windows,
                shift_pairs=shift_pairs,
                shift_cap=shift_cap,
                open_h=open_h,
                close_h=close_h,
            ):
                covering.append(ek)

        if len(covering) >= need:
            continue

        short = need - len(covering)
        ts = day_ts[di]
        wd_need = int(pd.Timestamp(ts).dayofweek)
        label_wd = _WEEKDAY_RU[wd_need] if 0 <= wd_need < 7 else "?"
        date_s = pd.Timestamp(ts).strftime("%Y-%m-%d")

        donors: list[tuple[str, str]] = []
        for ek in roster_keys:
            if ek in covering:
                continue
            ref_days: list[str] = []
            for di2 in range(n_days):
                if di2 == di:
                    continue
                if _geometric_can_cover_hour(
                    ek,
                    di2,
                    hour,
                    day_ts=day_ts,
                    windows=windows,
                    shift_pairs=shift_pairs,
                    shift_cap=shift_cap,
                    open_h=open_h,
                    close_h=close_h,
                ):
                    ts2 = day_ts[di2]
                    wd2 = int(pd.Timestamp(ts2).dayofweek)
                    if 0 <= wd2 < 7:
                        ref_days.append(_WEEKDAY_RU[wd2])
            if ref_days:
                uniq = []
                for x in ref_days:
                    if x not in uniq:
                        uniq.append(x)
                donors.append((ek, ", ".join(uniq[:5])))

        tip = (
            f"{date_s} ({label_wd}), {hour}:00, станция {st}: не хватает ~{short} чел. "
            f"(доступно по окнам {len(covering)}, нужно {need})."
        )
        if donors:
            parts = []
            for ek, refs in donors[:max_donors_per_slot]:
                nm = roster_display.get(ek, ek)
                parts.append(f"{nm}: уже есть пересечение с этим часом в другие дни ({refs}) — добавьте строку в sched для {label_wd}")
            tip += " Рассмотреть: " + "; ".join(parts) + "."
        else:
            tip += (
                " Нет сотрудников с таким же часом в другие дни — расширьте доступность или усильте штат."
            )

        hints.append(tip)
        if len(hints) >= max_slots:
            break

    return hints
