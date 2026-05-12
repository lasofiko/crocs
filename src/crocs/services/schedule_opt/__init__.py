"""Назначение смен: общая постановка + солверы PuLP / Pyomo / CP-SAT."""

from __future__ import annotations

from typing import Any

from crocs.services.schedule_opt.build_problem import (
    ShiftAssignmentProblem,
    ShiftOption,
    build_shift_assignment_problem,
    clock_hours,
    dedupe_shift_options,
    demand_grid,
    nid,
    parse_shifts,
    sched_windows,
    station_penalties,
)
from crocs.services.schedule_opt.solve_cp_sat import solve_schedule_cp_sat

__all__ = [
    "ShiftAssignmentProblem",
    "ShiftOption",
    "build_shift_assignment_problem",
    "clock_hours",
    "dedupe_shift_options",
    "demand_grid",
    "nid",
    "parse_shifts",
    "sched_windows",
    "station_penalties",
    "solve_schedule_cp_sat",
    "solve_schedule_pulp",
    "solve_schedule_pyomo",
]


def __getattr__(name: str) -> Any:
    """PuLP/Pyomo подгружаются только при обращении — не нужны для CP-SAT и старта CLI."""
    if name == "solve_schedule_pulp":
        from crocs.services.schedule_opt.solve_pulp import solve_schedule_pulp

        return solve_schedule_pulp
    if name == "solve_schedule_pyomo":
        from crocs.services.schedule_opt.solve_pyomo import solve_schedule_pyomo

        return solve_schedule_pyomo
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
