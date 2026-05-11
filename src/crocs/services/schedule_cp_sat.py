from __future__ import annotations

"""Расписание: CP-SAT (OR-Tools). Постановка задачи — в schedule_shift_problem."""

import math
import os
import sys
import threading
import time
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_shift_problem import build_shift_assignment_problem

_CP_SAT_DEFAULT_MAX_TIME_S = 300.0


def _cp_sat_worker_count() -> int:
    raw = os.environ.get("CROCS_CP_SAT_WORKERS", "").strip()
    if raw.isdigit():
        return max(1, min(32, int(raw)))
    ncpu = os.cpu_count() or 4
    workers = min(8, max(1, ncpu))
    if sys.platform == "win32":
        workers = min(workers, 4)
    return workers


def _heartbeat_enabled() -> bool:
    raw = os.environ.get("CROCS_CP_SAT_HEARTBEAT", "").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _cp_status_label(st: int) -> str:
    for name in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "MODEL_INVALID", "UNKNOWN"):
        if hasattr(cp_model, name) and int(getattr(cp_model, name)) == int(st):
            return name
    return f"STATUS_{st}"


def _solve_with_heartbeat(solver: cp_model.CpSolver, model: cp_model.CpModel, limit_s: float) -> int:
    stop = threading.Event()
    t0 = time.perf_counter()

    def _tick() -> None:
        interval = 45.0
        while not stop.wait(interval):
            elapsed = time.perf_counter() - t0
            print(
                f"CP-SAT: все еще считает... ~{elapsed:.0f}s, лимит времени <= {limit_s:g}s (не закрывайте окно).",
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
    roster_keys = prob.roster_keys
    demand = prob.demand
    day_ts = prob.day_ts
    max_extra = prob.max_extra
    coverage_idxs = prob.coverage_idxs
    by_emp_day = prob.by_emp_day
    by_emp = prob.by_emp
    max_sh = prob.max_shifts_per_employee_week
    week_cap = prob.week_cap

    model = cp_model.CpModel()
    x = [model.NewBoolVar(f"x_{i}") for i in range(len(options))]

    for _ek_d, idxs in by_emp_day.items():
        model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) <= 1)

    for key, req in demand.items():
        di, hour, st = key
        idxs = coverage_idxs.get((di, hour, st), [])
        if req == 0:
            if idxs:
                model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) <= max_extra)
            continue
        if not idxs:
            ds_label = pd.Timestamp(day_ts[di]).strftime("%Y-%m-%d (%A)")
            hint = (
                "В sched.csv колонка day: понедельник=1 ... воскресенье=7. "
                "Окно starttime..finishtime должно допускать смену из shifts.csv на этот час; "
                f"проверьте shift_limit. Дата={ds_label}."
            )
            raise ScheduleError(
                f"Нет ни одной допустимой смены под спрос: день index={di}, час={hour}, "
                f"станция={st}, нужно={req}. {hint}",
            )
        model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) >= req)
        model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) <= req + max_extra)

    for ek in roster_keys:
        idxs = by_emp[ek]
        wc = week_cap.get(ek)
        if wc is not None and idxs:
            cap_w = max(0, math.ceil(float(wc) - 1e-9))
            model.Add(
                cp_model.LinearExpr.Sum([x[j] * int(options[j].duration) for j in idxs]) <= cap_w
            )
        if idxs:
            model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) <= max_sh)
            if inputs.require_one_shift_per_sched_employee:
                model.Add(cp_model.LinearExpr.Sum([x[j] for j in idxs]) >= 1)

    obj_terms: list[cp_model.LinearExpr] = []
    for i, opt in enumerate(options):
        obj_terms.append(x[i] * int(opt.objective_coeff()))

    model.Minimize(cp_model.LinearExpr.Sum(obj_terms))

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
        f"(solver_time_limit_seconds в YAML; если null - берется {_CP_SAT_DEFAULT_MAX_TIME_S:g}s)",
        flush=True,
    )

    solver.parameters.num_search_workers = workers

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

    return pd.DataFrame(rows_out)
