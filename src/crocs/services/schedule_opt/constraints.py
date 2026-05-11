"""
Единое описание ограничений MILP/CP-SAT для задачи назначения смен.

Один проход по данным постановки — три солвера только подставляют свой синтаксис.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_opt.build_problem import ShiftAssignmentProblem, ShiftOption


@dataclass(frozen=True)
class AtMostOnePerEmpDay:
    """Не более одной смены у сотрудника в календарный день горизонта."""

    var_indices: tuple[int, ...]


@dataclass(frozen=True)
class CoveragePositive:
    """Слот со спросом > 0: покрытие в диапазоне [lower, upper]."""

    var_indices: tuple[int, ...]
    lower: int
    upper: int


@dataclass(frozen=True)
class CoverageSoftShortfall:
    """Спрос > 0: жёстко не ниже lower_hard (обычно 1), цель target (спрос); недобор наказывается в цели."""

    var_indices: tuple[int, ...]
    lower_hard: int
    target: int
    upper: int


@dataclass(frozen=True)
class CoverageZeroCap:
    """Слот со спросом 0: не более upper дополнительных людей сверх необходимости."""

    var_indices: tuple[int, ...]
    upper: int


@dataclass(frozen=True)
class EmployeeWeekHours:
    """Сумма часов смен за неделю не выше cap."""

    var_indices: tuple[int, ...]
    durations: tuple[int, ...]
    cap: int


@dataclass(frozen=True)
class EmployeeMaxShiftsWeek:
    """Не более max_shifts смен за неделю."""

    var_indices: tuple[int, ...]
    max_shifts: int


@dataclass(frozen=True)
class EmployeeMinOneShift:
    """Хотя бы одна смена за неделю (если включено в конфиге)."""

    var_indices: tuple[int, ...]


AssignmentConstraint = (
    AtMostOnePerEmpDay
    | CoveragePositive
    | CoverageSoftShortfall
    | CoverageZeroCap
    | EmployeeWeekHours
    | EmployeeMaxShiftsWeek
    | EmployeeMinOneShift
)


def collect_assignment_constraints(
    prob: ShiftAssignmentProblem,
    inputs: SchedulingInputs,
) -> list[AssignmentConstraint]:
    """Собирает все ограничения одним проходом (без повторной сборки генератором в солверах)."""

    max_extra = prob.max_extra
    durs_by_idx = prob.shift_duration_hours
    out: list[AssignmentConstraint] = []

    for idxs in prob.by_emp_day.values():
        out.append(AtMostOnePerEmpDay(tuple(idxs)))

    for key, req in prob.demand.items():
        di, hour, st = key
        idxs = prob.coverage_idxs.get((di, hour, st), [])
        if req == 0:
            if idxs:
                out.append(CoverageZeroCap(tuple(idxs), max_extra))
            continue
        if not idxs:
            ds_label = pd.Timestamp(prob.day_ts[di]).strftime("%Y-%m-%d (%A)")
            hint = (
                "В sched.csv колонка day: понедельник=1 ... воскресенье=7. "
                "Окно starttime..finishtime должно допускать смену из shifts.csv на этот час; "
                f"проверьте shift_limit. Дата={ds_label}."
            )
            raise ScheduleError(
                f"Нет ни одной допустимой смены под спрос: день index={di}, час={hour}, "
                f"станция={st}, нужно={req}. {hint}",
            )
        lo = int(req)
        hi = int(req) + max_extra
        if inputs.coverage_understaff_penalty > 0:
            lh = 1 if lo >= 1 else 0
            out.append(CoverageSoftShortfall(tuple(idxs), lh, lo, hi))
        else:
            out.append(CoveragePositive(tuple(idxs), lo, hi))

    max_sh = prob.max_shifts_per_employee_week
    for ek in prob.roster_keys:
        idxs = prob.by_emp[ek]
        wc = prob.week_cap.get(ek)
        if wc is not None and idxs:
            cap_w = max(0, math.ceil(float(wc) - 1e-9))
            durs = tuple(int(durs_by_idx[j]) for j in idxs)
            out.append(EmployeeWeekHours(tuple(idxs), durs, cap_w))
        if idxs:
            out.append(EmployeeMaxShiftsWeek(tuple(idxs), max_sh))
            if inputs.require_one_shift_per_sched_employee:
                out.append(EmployeeMinOneShift(tuple(idxs)))
    return out


def schedule_rows_from_solution(
    options: list[ShiftOption],
    x_active: list[bool],
) -> list[dict[str, Any]]:
    rows_out: list[dict[str, Any]] = []
    for i, opt in enumerate(options):
        if i >= len(x_active) or not x_active[i]:
            continue
        rows_out.append(
            {
                "ds": pd.Timestamp(opt.ds).strftime("%Y-%m-%d"),
                "station_key": opt.station,
                "employee_id": opt.emp_display,
                "starttime": float(opt.start_h),
                "finishtime": float(opt.start_h + opt.duration),
            }
        )
    return rows_out
