"""Pyomo + CBC/HiGHS: решение задачи назначения смен."""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import pyomo.environ as pe
from pyomo.opt import TerminationCondition

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
        "Добавьте CBC в PATH (COIN-OR) или установите highspy для HiGHS.",
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
    n = len(options)
    if n == 0:
        raise ScheduleError("no shift options for Pyomo model")

    model = pe.ConcreteModel(name="shift_assign")
    model.I = pe.RangeSet(0, n - 1)
    model.x = pe.Var(model.I, domain=pe.Binary)

    coeffs = {i: int(c) for i, c in enumerate(prob.objective_coeffs)}

    model.cons = pe.ConstraintList()
    under_sf: list[Any] = []

    for con in collect_assignment_constraints(prob, inputs):
        if isinstance(con, AtMostOnePerEmpDay):
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) <= 1)
        elif isinstance(con, CoveragePositive):
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) >= con.lower)
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) <= con.upper)
        elif isinstance(con, CoverageSoftShortfall):
            mx = max(0, con.target - con.lower_hard)
            sf = pe.Var(bounds=(0, mx))
            model.add_component(f"sf_{len(under_sf)}", sf)
            under_sf.append(sf)
            sx = pe.quicksum(model.x[j] for j in con.var_indices)
            if con.lower_hard > 0:
                model.cons.add(sx >= con.lower_hard)
            model.cons.add(sx <= con.upper)
            model.cons.add(sx + sf >= con.target)
        elif isinstance(con, CoverageZeroCap):
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) <= con.upper)
        elif isinstance(con, EmployeeWeekHours):
            model.cons.add(
                pe.quicksum(
                    model.x[j] * int(con.durations[k])
                    for k, j in enumerate(con.var_indices)
                )
                <= con.cap
            )
        elif isinstance(con, EmployeeMaxShiftsWeek):
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) <= con.max_shifts)
        elif isinstance(con, EmployeeMinOneShift):
            model.cons.add(pe.quicksum(model.x[j] for j in con.var_indices) >= 1)

    obj_expr = pe.quicksum(model.x[i] * coeffs[i] for i in range(n))
    wp = int(inputs.coverage_understaff_penalty)
    if under_sf and wp > 0:
        obj_expr += wp * pe.quicksum(under_sf)
    model.obj = pe.Objective(expr=obj_expr, sense=pe.minimize)

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
            msg += " Попробуйте отключить require_one_shift_per_sched_employee или сократите sched."
        raise ScheduleError(msg)

    if tc not in (
        TerminationCondition.optimal,
        TerminationCondition.locallyOptimal,
        TerminationCondition.feasible,
        TerminationCondition.maxTimeLimit,
    ):
        raise ScheduleError(
            f"MILP (Pyomo): неожиданный статус солвера: {tc}. "
            "Увеличьте scheduling.solver_time_limit_seconds или ослабьте ограничения в YAML.",
        )

    x_active: list[bool] = []
    for i in range(n):
        try:
            val = pe.value(model.x[i])
        except (ValueError, TypeError):
            val = 0.0
        x_active.append(val is not None and float(val) >= 0.5)

    rows_out = schedule_rows_from_solution(options, x_active)

    if not rows_out:
        raise ScheduleError("MILP (Pyomo): пустое расписание (все x≈0 или решение не разобрано).")

    return pd.DataFrame(rows_out)
