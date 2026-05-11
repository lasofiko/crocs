"""Расписание: MILP через Pyomo (CBC или HiGHS)."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import pyomo.environ as pe
from pyomo.opt import TerminationCondition

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_shift_problem import build_shift_assignment_problem

_MILP_DEFAULT_TIME_S = 300.0


def _resolve_milp_solver(preference: str) -> tuple[Any, str]:
    pref = (preference or "auto").strip().lower()
    order: list[str]
    if pref == "cbc":
        order = ["cbc"]
    elif pref in ("highs", "highspy"):
        order = ["highs", "appsi_highs"]
    else:
        order = ["highs", "appsi_highs", "cbc"]
    for name in order:
        sol = pe.SolverFactory(name)
        if sol.available(False):
            return sol, name
    raise ScheduleError(
        "Pyomo: не найден доступный MILP-солвер (highs или cbc). "
        "Добавьте CBC в PATH (COIN-OR) или установите highspy для HiGHS."
    )


def _milp_time_limit_seconds(inputs: SchedulingInputs) -> float:
    if inputs.solver_time_limit_seconds is not None:
        return float(inputs.solver_time_limit_seconds)
    return _MILP_DEFAULT_TIME_S


def _apply_solver_options(solver: Any, name: str, limit_s: float) -> None:
    lim = max(1.0, float(limit_s))
    ln = name.lower()
    if ln == "cbc":
        solver.options["seconds"] = int(math.ceil(lim))
        solver.options["ratio"] = 0.0
    elif ln in ("highs", "appsi_highs"):
        solver.options["time_limit"] = lim
    else:
        solver.options["seconds"] = int(math.ceil(lim))


def solve_schedule_pyomo(inputs: SchedulingInputs) -> pd.DataFrame:
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

    n = len(options)
    if n == 0:
        raise ScheduleError("no shift options for Pyomo model")

    model = pe.ConcreteModel(name="shift_assign")
    model.I = pe.RangeSet(0, n - 1)
    model.x = pe.Var(model.I, domain=pe.Binary)

    coeffs = {i: int(options[i].objective_coeff()) for i in range(n)}

    def obj_rule(m: Any) -> Any:
        return pe.quicksum(m.x[i] * coeffs[i] for i in range(n))

    model.obj = pe.Objective(rule=obj_rule, sense=pe.minimize)

    model.cons = pe.ConstraintList()
    for _ek_d, idxs in by_emp_day.items():
        model.cons.add(pe.quicksum(model.x[j] for j in idxs) <= 1)

    for key, req in demand.items():
        di, hour, st = key
        idxs = coverage_idxs.get((di, hour, st), [])
        if req == 0:
            if idxs:
                model.cons.add(pe.quicksum(model.x[j] for j in idxs) <= max_extra)
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
        model.cons.add(pe.quicksum(model.x[j] for j in idxs) >= int(req))
        model.cons.add(pe.quicksum(model.x[j] for j in idxs) <= int(req) + max_extra)

    for ek in roster_keys:
        idxs = by_emp[ek]
        wc = week_cap.get(ek)
        if wc is not None and idxs:
            cap_w = max(0, math.ceil(float(wc) - 1e-9))
            model.cons.add(
                pe.quicksum(model.x[j] * int(options[j].duration) for j in idxs) <= cap_w
            )
        if idxs:
            model.cons.add(pe.quicksum(model.x[j] for j in idxs) <= max_sh)
            if inputs.require_one_shift_per_sched_employee:
                model.cons.add(pe.quicksum(model.x[j] for j in idxs) >= 1)

    limit_s = _milp_time_limit_seconds(inputs)
    solver, solver_name = _resolve_milp_solver(inputs.milp_solver)
    _apply_solver_options(solver, solver_name, limit_s)

    print(
        f"Pyomo MILP: переменных={n}, солвер={solver_name}, лимит≈{limit_s:g}s.",
        flush=True,
    )

    results = solver.solve(model, tee=False)
    tc = results.solver.termination_condition

    if tc == TerminationCondition.infeasible:
        msg = "MILP (Pyomo): модель недостижима (INFEASIBLE)."
        if inputs.min_employees_per_station >= 2:
            msg += " Попробуйте configs/relaxed_scheduling.yaml (min_employees_per_station: 1)."
        if inputs.require_one_shift_per_sched_employee:
            msg += (
                " Проверьте require_one_shift_per_sched_employee или сократите sched."
            )
        raise ScheduleError(msg)

    if tc not in (
        TerminationCondition.optimal,
        TerminationCondition.locallyOptimal,
        TerminationCondition.feasible,
        TerminationCondition.maxTimeLimit,  # допускаем лучшее найденное
    ):
        raise ScheduleError(
            f"MILP (Pyomo): неожиданный статус солвера: {tc}. "
            "Увеличьте scheduling.solver_time_limit_seconds или ослабьте ограничения в YAML.",
        )

    rows_out: list[dict[str, Any]] = []
    for i in range(n):
        try:
            val = pe.value(model.x[i])
        except (ValueError, TypeError):
            val = 0.0
        if val is None or val < 0.5:
            continue
        opt = options[i]
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
        raise ScheduleError("MILP (Pyomo): пустое расписание (все x≈0 или решение не разобрано).")

    return pd.DataFrame(rows_out)
