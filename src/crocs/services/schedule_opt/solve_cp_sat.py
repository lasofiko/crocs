"""CP-SAT (OR-Tools): решение задачи назначения смен."""

from __future__ import annotations

import multiprocessing
import os
import threading
import time
from collections import defaultdict
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_opt.build_problem import (
    ShiftAssignmentProblem,
    build_shift_assignment_problem,
)
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

_CP_SAT_DEFAULT_MAX_TIME_S = 300.0
_CP_SAT_WORKERS_CACHED: int | None = None


def _cp_sat_worker_count() -> int:
    global _CP_SAT_WORKERS_CACHED
    if _CP_SAT_WORKERS_CACHED is not None:
        return _CP_SAT_WORKERS_CACHED
    raw = os.environ.get("CROCS_CP_SAT_WORKERS", "").strip()
    if raw.isdigit():
        _CP_SAT_WORKERS_CACHED = max(1, int(raw))
        return _CP_SAT_WORKERS_CACHED
    ncpu = multiprocessing.cpu_count() or os.cpu_count() or 4
    workers = max(1, int(ncpu))
    _CP_SAT_WORKERS_CACHED = workers
    return _CP_SAT_WORKERS_CACHED


def _heartbeat_enabled() -> bool:
    raw = os.environ.get("CROCS_CP_SAT_HEARTBEAT", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _cp_status_label(st: int) -> str:
    for name in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "MODEL_INVALID", "UNKNOWN"):
        if hasattr(cp_model, name) and int(getattr(cp_model, name)) == int(st):
            return name
    return f"STATUS_{st}"


def _greedy_hint_indices(prob: ShiftAssignmentProblem, inputs: SchedulingInputs) -> list[int]:
    """Жадное допустимое частичное решение: подсказки для CP-SAT (не обязаны быть оптимальными).

    Сначала рассматриваются смены людей с большим недельным лимитом часов (staff_limits → week_cap),
    без лимита — впереди; внутри группы — дешевле по целевому коэффициенту смены.
    """

    def week_hour_budget(ek: str) -> float:
        cap = prob.week_cap.get(ek)
        if cap is None:
            return float("inf")
        return float(cap)

    n = len(prob.options)
    if n == 0:
        return []

    hours_fs = frozenset(prob.hours)
    cov: dict[tuple[int, int, str], int] = {}
    emp_day_used: set[tuple[str, int]] = set()
    emp_shifts: dict[str, int] = defaultdict(int)
    emp_hours: dict[str, float] = defaultdict(float)

    order = sorted(
        range(n),
        key=lambda i: (
            -week_hour_budget(prob.options[i].emp_key),
            prob.objective_coeffs[i],
            i,
        ),
    )
    chosen: list[int] = []

    def can_take(i: int) -> bool:
        opt = prob.options[i]
        ed = (opt.emp_key, opt.day_idx)
        if ed in emp_day_used:
            return False
        ek = opt.emp_key
        if emp_shifts[ek] >= prob.max_shifts_per_employee_week:
            return False
        wc = prob.week_cap.get(ek)
        if wc is not None and emp_hours[ek] + opt.duration > wc + 1e-9:
            return False
        return True

    def marginal_need(i: int) -> int:
        opt = prob.options[i]
        score = 0
        for h in range(opt.start_h, opt.start_h + opt.duration):
            if h not in hours_fs:
                continue
            key = (opt.day_idx, h, opt.station)
            req = prob.demand.get(key, 0)
            if req <= 0:
                continue
            cur = cov.get(key, 0)
            if cur < req:
                score += int(req) - cur
        return score

    def take(i: int) -> None:
        opt = prob.options[i]
        emp_day_used.add((opt.emp_key, opt.day_idx))
        emp_shifts[opt.emp_key] += 1
        emp_hours[opt.emp_key] += float(opt.duration)
        chosen.append(i)
        for h in range(opt.start_h, opt.start_h + opt.duration):
            if h not in hours_fs:
                continue
            key = (opt.day_idx, h, opt.station)
            cov[key] = cov.get(key, 0) + 1

    for i in order:
        if not can_take(i) or marginal_need(i) <= 0:
            continue
        take(i)

    if inputs.require_one_shift_per_sched_employee:
        for ek in prob.roster_keys:
            if emp_shifts[ek] > 0:
                continue
            candidates = [j for j in prob.by_emp[ek] if can_take(j)]
            if not candidates:
                continue
            best = min(
                candidates,
                key=lambda j: (
                    -week_hour_budget(prob.options[j].emp_key),
                    prob.objective_coeffs[j],
                    j,
                ),
            )
            take(best)

    return chosen


def _solve_with_heartbeat(solver: cp_model.CpSolver, model: cp_model.CpModel, limit_s: float) -> int:
    stop = threading.Event()
    t0 = time.perf_counter()

    def _tick() -> None:
        interval = 45.0
        while not stop.wait(interval):
            elapsed = time.perf_counter() - t0
            print(
                f"CP-SAT: все еще считает... ~{elapsed:.0f}s, лимит времени <= {limit_s:g}s.",
                flush=True,
            )

    th = threading.Thread(target=_tick, daemon=True)
    th.start()
    try:
        return int(solver.Solve(model))
    finally:
        stop.set()


def solve_schedule_cp_sat(inputs: SchedulingInputs) -> pd.DataFrame:
    prob = build_shift_assignment_problem(inputs)
    options = prob.options
    n = len(options)

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x_{i}") for i in range(n)]

    obj_c = prob.objective_coeffs
    obj_terms: list[cp_model.LinearExpr] = [
        x[i] * int(obj_c[i]) for i in range(n)
    ]

    sf_seq = 0
    for con in collect_assignment_constraints(prob, inputs):
        if isinstance(con, AtMostOnePerEmpDay):
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) <= 1)
        elif isinstance(con, CoveragePositive):
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) >= con.lower)
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) <= con.upper)
        elif isinstance(con, CoverageSoftShortfall):
            sx = cp_model.LinearExpr.Sum([x[j] for j in con.var_indices])
            if con.lower_hard > 0:
                model.Add(sx >= con.lower_hard)
            model.Add(sx <= con.upper)
            mx = max(0, con.target - con.lower_hard)
            sf = model.NewIntVar(0, mx, f"sf_{sf_seq}")
            sf_seq += 1
            model.Add(sx + sf >= con.target)
            obj_terms.append(sf * int(inputs.coverage_understaff_penalty))
        elif isinstance(con, CoverageZeroCap):
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) <= con.upper)
        elif isinstance(con, EmployeeWeekHours):
            terms = [x[j] * int(con.durations[k]) for k, j in enumerate(con.var_indices)]
            model.Add(cp_model.LinearExpr.Sum(terms) <= con.cap)
        elif isinstance(con, EmployeeMaxShiftsWeek):
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) <= con.max_shifts)
        elif isinstance(con, EmployeeMinOneShift):
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in con.var_indices]) >= 1)

    model.Minimize(cp_model.LinearExpr.Sum(obj_terms))

    ws = os.environ.get("CROCS_CP_SAT_NO_WARM_START", "").strip().lower()
    if ws not in ("1", "true", "yes", "on"):
        for idx in _greedy_hint_indices(prob, inputs):
            model.add_hint(x[idx], 1)

    solver = cp_model.CpSolver()
    if inputs.solver_time_limit_seconds is not None:
        solver.parameters.max_time_in_seconds = float(inputs.solver_time_limit_seconds)
    else:
        solver.parameters.max_time_in_seconds = _CP_SAT_DEFAULT_MAX_TIME_S

    limit_note = (
        float(inputs.solver_time_limit_seconds)
        if inputs.solver_time_limit_seconds is not None
        else _CP_SAT_DEFAULT_MAX_TIME_S
    )
    workers = _cp_sat_worker_count()
    print(
        f"CP-SAT: переменных={len(x)}, потоков={workers}, лимит={limit_note:g}s "
        f"(solver_time_limit_seconds в YAML; если null — {_CP_SAT_DEFAULT_MAX_TIME_S:g}s)",
        flush=True,
    )

    solver.parameters.num_search_workers = workers
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_presolve = True
    solver.parameters.log_search_progress = False

    t_solve0 = time.perf_counter()
    if _heartbeat_enabled():
        status = _solve_with_heartbeat(solver, model, limit_note)
    else:
        status = int(solver.Solve(model))
    solve_secs = time.perf_counter() - t_solve0
    print(
        f"CP-SAT: поиск завершен за {solve_secs:.1f}s, статус={_cp_status_label(status)}.",
        flush=True,
    )

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        base = (
            "CP-SAT: нет допустимого расписания или решатель не успел "
            f"(status={_cp_status_label(status)})."
        )
        if status == cp_model.INFEASIBLE:
            parts: list[str] = ["Модель недостижима."]
            if inputs.min_employees_per_station >= 2:
                parts.append(
                    "Попробуйте configs/relaxed_scheduling.yaml (min_employees_per_station: 1)."
                )
            if inputs.require_one_shift_per_sched_employee:
                parts.append(
                    "Включено require_one_shift_per_sched_employee: у каждого из sched нужна ≥1 смена за неделю; "
                    "в relaxed YAML это false или сократите список в sched."
                )
            parts.append(
                "Или расширьте окна starttime/finishtime в sched.csv / shifts.csv, проверьте staff_limits."
            )
            hint = " " + " ".join(parts)
        elif status == cp_model.UNKNOWN:
            hint = (
                " Решатель не успел за лимит времени: увеличьте scheduling.solver_time_limit_seconds "
                f"(сейчас эффективно до {limit_note:g}s) или запустите с configs/relaxed_scheduling.yaml."
            )
        else:
            hint = " См. scheduling.* в YAML и входные sched/shifts/staff_limits."
        raise ScheduleError(base + hint)

    x_active = [solver.Value(x[i]) == 1 for i in range(n)]
    rows_out = schedule_rows_from_solution(options, x_active)

    if not rows_out:
        raise ScheduleError("solver returned an empty schedule")

    return pd.DataFrame(rows_out)
