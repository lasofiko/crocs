"""Назначение смен: общая постановка + солверы PuLP / Pyomo / CP-SAT."""

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
from crocs.services.schedule_opt.solve_pulp import solve_schedule_pulp
from crocs.services.schedule_opt.solve_pyomo import solve_schedule_pyomo

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
