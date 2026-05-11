"""PuLP + CBC/HiGHS: решение задачи назначения смен."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_opt.build_problem import build_shift_assignment_problem
from crocs.services.schedule_opt.constraints import (
    AtMostOnePerEmpDay,
    CoveragePositive,
    CoverageSoftShortfall,
    CoverageZeroCap,
    EmployeeMaxShiftsWeek,
    EmployeeMinOneShift,
    EmployeeWeekHours,
    collect_assignment_constraints,
    schedule_rows_from_solution,
)

_MILP_DEFAULT_TIME_S = 300.0
_MILP_GAP_REL_DEFAULT = 0.02
_MILP_GAP_REL_CACHED: float | None = None


def _import_pulp() -> Any:
    try:
        import pulp  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise ScheduleError(
            "PuLP не установлен. Установите зависимость `pulp` "
            "или переключите scheduling.schedule_engine на cp_sat/pyomo.",
        ) from exc
    return pulp


def _milp_time_limit_seconds(inputs: SchedulingInputs) -> float:
    """Лимит секунд для CBC/HiGHS. Без лимита (бенч): CROCS_MILP_NO_TIME_LIMIT=1."""
    raw = os.environ.get("CROCS_MILP_NO_TIME_LIMIT", "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        # CBC принимает большое целое; «год» достаточно для практики.
        return float(86400 * 365)
    if inputs.solver_time_limit_seconds is not None:
        return max(1.0, float(inputs.solver_time_limit_seconds))
    return _MILP_DEFAULT_TIME_S


def _milp_gap_rel() -> float:
    global _MILP_GAP_REL_CACHED
    if _MILP_GAP_REL_CACHED is not None:
        return _MILP_GAP_REL_CACHED
    raw = os.environ.get("CROCS_MILP_GAP_REL", "").strip()
    if raw:
        try:
            _MILP_GAP_REL_CACHED = max(0.0, min(0.5, float(raw)))
        except ValueError:
            _MILP_GAP_REL_CACHED = _MILP_GAP_REL_DEFAULT
    else:
        _MILP_GAP_REL_CACHED = _MILP_GAP_REL_DEFAULT
    return _MILP_GAP_REL_CACHED


def _resolve_pulp_solver(pulp: Any, preference: str, limit_s: float) -> tuple[Any, str]:
    pref = (preference or "auto").strip().lower()
    if pref not in ("auto", "cbc", "highs"):
        pref = "auto"

    gap = _milp_gap_rel()
    order = ["highs", "cbc"] if pref == "auto" else [pref]
    for name in order:
        if name == "highs":
            try:
                solver = pulp.HiGHS_CMD(msg=False, timeLimit=float(limit_s))
                if bool(solver.available()):
                    return solver, "highs"
            except Exception:
                continue
        if name == "cbc":
            try:
                solver = pulp.PULP_CBC_CMD(
                    msg=False,
                    timeLimit=float(limit_s),
                    gapRel=gap,
                )
                if bool(solver.available()):
                    return solver, "cbc"
            except Exception:
                continue

    raise ScheduleError(
        "PuLP: не найден доступный MILP-солвер (CBC/HiGHS). "
        "Установите CBC/HiGHS в PATH или используйте cp_sat.",
    )


def solve_schedule_pulp(inputs: SchedulingInputs) -> pd.DataFrame:
    pulp = _import_pulp()
    prob = build_shift_assignment_problem(inputs)
    options = prob.options
    n = len(options)
    if n == 0:
        raise ScheduleError("no shift options for PuLP model")

    model = pulp.LpProblem("shift_assign", pulp.LpMinimize)
    x = [pulp.LpVariable(f"x_{i}", lowBound=0, upBound=1, cat=pulp.LpBinary) for i in range(n)]
    obj_c = prob.objective_coeffs
    under_vars: list[Any] = []

    for con in collect_assignment_constraints(prob, inputs):
        if isinstance(con, AtMostOnePerEmpDay):
            model += pulp.lpSum(x[j] for j in con.var_indices) <= 1
        elif isinstance(con, CoveragePositive):
            model += pulp.lpSum(x[j] for j in con.var_indices) >= con.lower
            model += pulp.lpSum(x[j] for j in con.var_indices) <= con.upper
        elif isinstance(con, CoverageSoftShortfall):
            mx = max(0, con.target - con.lower_hard)
            sf = pulp.LpVariable(
                f"sf_{len(under_vars)}",
                lowBound=0,
                upBound=mx,
                cat=pulp.LpInteger,
            )
            under_vars.append(sf)
            sx = pulp.lpSum(x[j] for j in con.var_indices)
            if con.lower_hard > 0:
                model += sx >= con.lower_hard
            model += sx <= con.upper
            model += sx + sf >= con.target
        elif isinstance(con, CoverageZeroCap):
            model += pulp.lpSum(x[j] for j in con.var_indices) <= con.upper
        elif isinstance(con, EmployeeWeekHours):
            model += (
                pulp.lpSum(x[j] * int(con.durations[k]) for k, j in enumerate(con.var_indices))
                <= con.cap
            )
        elif isinstance(con, EmployeeMaxShiftsWeek):
            model += pulp.lpSum(x[j] for j in con.var_indices) <= con.max_shifts
        elif isinstance(con, EmployeeMinOneShift):
            model += pulp.lpSum(x[j] for j in con.var_indices) >= 1

    obj_expr = pulp.lpSum(x[i] * int(obj_c[i]) for i in range(n))
    if under_vars:
        w = int(inputs.coverage_understaff_penalty)
        obj_expr += w * pulp.lpSum(under_vars)
    model += obj_expr

    limit_s = _milp_time_limit_seconds(inputs)
    solver, solver_name = _resolve_pulp_solver(pulp, inputs.milp_solver, limit_s)
    lim_note = "без лимита (CROCS_MILP_NO_TIME_LIMIT)" if limit_s >= float(86400 * 30) else f"{limit_s:g}s"
    print(f"PuLP MILP: переменных={n}, солвер={solver_name}, лимит≈{lim_note}.", flush=True)
    model.solve(solver)
    status = int(model.status)
    status_name = pulp.LpStatus.get(status, str(status))

    x_active = [
        x[i].value() is not None and float(x[i].value()) >= 0.5 for i in range(n)
    ]
    rows_out = schedule_rows_from_solution(options, x_active)

    if status_name.lower().startswith("infeasible"):
        msg = "MILP (PuLP): модель недостижима (INFEASIBLE)."
        if inputs.min_employees_per_station >= 2:
            msg += (
                " Попробуйте configs/relaxed_scheduling.yaml "
                "(больше времени солвера / ослабление require_one_shift и max_extra; минимум на станции можно держать 2)."
            )
        if inputs.require_one_shift_per_sched_employee:
            msg += " Проверьте require_one_shift_per_sched_employee или сократите sched."
        raise ScheduleError(msg)

    if status_name not in ("Optimal", "Not Solved") and not rows_out:
        raise ScheduleError(
            f"MILP (PuLP): неожиданный статус солвера: {status_name}. "
            "Увеличьте scheduling.solver_time_limit_seconds или ослабьте ограничения в YAML.",
        )

    if not rows_out:
        raise ScheduleError("MILP (PuLP): пустое расписание (все x≈0 или решение не разобрано).")

    return pd.DataFrame(rows_out)
