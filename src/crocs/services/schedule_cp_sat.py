from __future__ import annotations

"""Расписание: OR-Tools CP-SAT + опциональный LNS/ALNS (перестройка окон по дням или по сотрудникам)."""

import math
import os
import random
import sys
import threading
import time
from typing import Any

import pandas as pd
from ortools.sat.python import cp_model

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_shift_problem import ShiftAssignmentProblem, ShiftOption, build_shift_assignment_problem

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


def _build_cp_sat_model(
    prob: ShiftAssignmentProblem,
    inputs: SchedulingInputs,
) -> tuple[cp_model.CpModel, list[cp_model.IntVar]]:
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
    return model, x


def _run_cp_solver(
    model: cp_model.CpModel,
    *,
    time_limit_seconds: float,
    use_heartbeat: bool,
    stop_after_first_solution: bool = False,
) -> tuple[int, cp_model.CpSolver]:
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit_seconds)
    solver.parameters.num_search_workers = _cp_sat_worker_count()
    if stop_after_first_solution:
        solver.parameters.stop_after_first_solution = True
    if use_heartbeat and _heartbeat_enabled():
        status = _solve_with_heartbeat(solver, model, time_limit_seconds)
    else:
        status = int(solver.Solve(model))
    return status, solver


def _rows_from_solver(solver: cp_model.CpSolver, x: list[cp_model.IntVar], options: list[ShiftOption]) -> pd.DataFrame:
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


def _rows_from_assignment(vals: dict[int, int], options: list[ShiftOption]) -> pd.DataFrame:
    rows_out: list[dict[str, Any]] = []
    for i, opt in enumerate(options):
        if vals.get(i, 0) != 1:
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
        raise ScheduleError("LNS produced an empty schedule")
    return pd.DataFrame(rows_out)


def _lns_repair_time_seconds(inputs: SchedulingInputs, main_limit: float) -> float:
    if inputs.lns_repair_seconds is not None:
        return max(1.0, float(inputs.lns_repair_seconds))
    return max(15.0, min(120.0, main_limit / 4.0))


def _lns_free_by_days(prob: ShiftAssignmentProblem, destroyed_day_idx: set[int]) -> set[int]:
    return {i for i, o in enumerate(prob.options) if o.day_idx in destroyed_day_idx}


def _lns_free_by_staff(prob: ShiftAssignmentProblem, emp_keys: set[str]) -> set[int]:
    return {i for i, o in enumerate(prob.options) if o.emp_key in emp_keys}


def _renorm_weights(w: list[float]) -> None:
    s = sum(w)
    if s <= 0:
        w[:] = [1.0, 0.0]
        return
    for i in range(len(w)):
        w[i] /= s


def _run_lns_improvement(
    prob: ShiftAssignmentProblem,
    inputs: SchedulingInputs,
    *,
    main_limit: float,
    initial_solver: cp_model.CpSolver,
    initial_x: list[cp_model.IntVar],
) -> dict[int, int]:
    n = len(prob.options)
    best_vals = {i: int(initial_solver.Value(initial_x[i])) for i in range(n)}
    best_obj = float(initial_solver.ObjectiveValue())

    n_days = len(prob.day_ts)
    roster = list(prob.roster_keys)
    dmin = max(1, min(inputs.lns_destroy_days_min, n_days))
    dmax = max(dmin, min(inputs.lns_destroy_days_max, n_days))
    repair_limit = _lns_repair_time_seconds(inputs, main_limit)
    iterations = max(1, int(inputs.lns_iterations))
    staff_frac = max(0.0, min(0.5, float(inputs.lns_staff_destroy_fraction)))

    weights = [1.0, 1.0 if staff_frac > 0 and len(roster) > 1 else 0.0]
    if weights[1] == 0.0:
        weights[0] = 1.0

    rng = random.Random(inputs.lns_seed)

    print(
        f"CP-SAT LNS: итераций={iterations}, ремонт до {repair_limit:g}s, "
        f"дни разрушения [{dmin},{dmax}], staff_frac={staff_frac:.2f}, старт obj={best_obj:.1f}",
        flush=True,
    )

    for it in range(iterations):
        w0, w1 = weights[0], weights[1]
        s = w0 + w1
        use_staff = s > 0 and w1 > 0 and (w0 == 0 or rng.random() < (w1 / s))

        if use_staff and roster:
            m = min(12, max(1, int(math.ceil(len(roster) * staff_frac))))
            chosen = set(rng.sample(roster, min(m, len(roster))))
            free = _lns_free_by_staff(prob, chosen)
            op_name = "staff"
        else:
            k = rng.randint(dmin, dmax)
            destroyed = set(rng.sample(range(n_days), k))
            free = _lns_free_by_days(prob, destroyed)
            op_name = "days"

        if not free:
            continue

        model_r, x_r = _build_cp_sat_model(prob, inputs)
        for j in range(n):
            if j not in free:
                model_r.Add(x_r[j] == best_vals[j])

        status, solver_r = _run_cp_solver(
            model_r,
            time_limit_seconds=repair_limit,
            use_heartbeat=False,
            stop_after_first_solution=True,
        )
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            if op_name == "days":
                weights[0] *= 0.92
            else:
                weights[1] *= 0.92
            _renorm_weights(weights)
            continue

        obj_r = float(solver_r.ObjectiveValue())
        improved = obj_r + 1e-6 < best_obj
        if improved:
            best_obj = obj_r
            best_vals = {i: int(solver_r.Value(x_r[i])) for i in range(n)}
            if op_name == "days":
                weights[0] *= 1.12
            else:
                weights[1] *= 1.12
            print(
                f"CP-SAT LNS: iter {it + 1}/{iterations} ({op_name}) улучшение obj={best_obj:.1f}",
                flush=True,
            )
        else:
            if op_name == "days":
                weights[0] *= 0.95
            else:
                weights[1] *= 0.95
        _renorm_weights(weights)

    print(f"CP-SAT LNS: итоговый obj={best_obj:.1f}", flush=True)
    return best_vals


def _raise_schedule_error(status: int, inputs: SchedulingInputs, limit_note: float) -> None:
    base = (
        "CP-SAT: нет допустимого расписания или решатель не успел "
        f"(status={_cp_status_label(status)})."
    )
    if status == cp_model.INFEASIBLE:
        parts: list[str] = ["Модель недостижима."]
        if inputs.min_employees_per_station >= 2:
            parts.append(
                "Попробуйте ослабить min_employees_per_station (например 1).",
            )
        if inputs.require_one_shift_per_sched_employee:
            parts.append(
                "Включено require_one_shift_per_sched_employee: у каждого из sched нужна ≥1 смена за неделю; "
                "выключите или сократите список в sched.",
            )
        parts.append(
            "Или расширьте окна starttime/finishtime в sched.csv / shifts.csv, проверьте staff_limits.",
        )
        hint = " " + " ".join(parts)
    elif status == cp_model.UNKNOWN:
        if inputs.cp_sat_stop_after_first_solution:
            hint = (
                " За лимит времени CP-SAT не нашёл ни одного допустимого расписания "
                f"(включён stop_after_first_solution; лимит ≈{limit_note:g}s). "
                "Это не «не успела оптимизация», а «нет ни одного подходящего набора смен за отведённое время» — "
                "увеличьте scheduling.solver_time_limit_seconds, временно ослабьте ограничения "
                "(min_employees_per_station, require_one_shift_per_sched_employee) или расширьте sched/shifts/staff_limits."
            )
        else:
            hint = (
                " Решатель не успел за лимит времени: увеличьте scheduling.solver_time_limit_seconds "
                f"(сейчас эффективно до {limit_note:g}s) или включите cp_sat_stop_after_first_solution для остановки на первом допустимом."
            )
    else:
        hint = " См. scheduling.* в YAML и входные sched/shifts/staff_limits."
    raise ScheduleError(base + hint)


def solve_schedule_cp_sat(inputs: SchedulingInputs) -> pd.DataFrame:
    prob = build_shift_assignment_problem(inputs)
    model, x = _build_cp_sat_model(prob, inputs)

    if inputs.solver_time_limit_seconds is not None:
        main_limit = float(inputs.solver_time_limit_seconds)
    else:
        main_limit = _CP_SAT_DEFAULT_MAX_TIME_S

    workers = _cp_sat_worker_count()
    print(
        f"CP-SAT: переменных={len(x)}, потоков={workers}, лимит={main_limit:g}s "
        f"(solver_time_limit_seconds; null → {_CP_SAT_DEFAULT_MAX_TIME_S:g}s), "
        f"LNS={'on' if inputs.lns_enabled else 'off'}, "
        f"first_solution_stop={'on' if inputs.cp_sat_stop_after_first_solution else 'off'}",
        flush=True,
    )

    t_solve0 = time.perf_counter()
    status, solver = _run_cp_solver(
        model,
        time_limit_seconds=main_limit,
        use_heartbeat=True,
        stop_after_first_solution=inputs.cp_sat_stop_after_first_solution,
    )
    solve_secs = time.perf_counter() - t_solve0
    print(
        f"CP-SAT: поиск завершен за {solve_secs:.1f}s, статус={_cp_status_label(status)}.",
        flush=True,
    )
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        _raise_schedule_error(status, inputs, main_limit)

    if inputs.lns_enabled:
        t1 = time.perf_counter()
        best_vals = _run_lns_improvement(
            prob,
            inputs,
            main_limit=main_limit,
            initial_solver=solver,
            initial_x=x,
        )
        print(f"CP-SAT LNS: локальный поиск за {time.perf_counter() - t1:.1f}s", flush=True)
        return _rows_from_assignment(best_vals, prob.options)

    return _rows_from_solver(solver, x, prob.options)
