"""MILP через Pyomo: тот же минимальный кейс, что и CP-SAT; пропуск без CBC/HiGHS."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("pyomo", reason="pyomo not installed")

import pyomo.environ as pe

from crocs.services.schedule_pyomo import solve_schedule_pyomo
from tests.test_schedule_cp_sat import _minimal_feasible_inputs


def _any_milp_solver() -> bool:
    for name in ("cbc", "highs", "appsi_highs"):
        if pe.SolverFactory(name).available(False):
            return True
    return False


@pytest.mark.skipif(not _any_milp_solver(), reason="no CBC/HiGHS available for Pyomo")
def test_pyomo_matches_cp_sat_shape_on_minimal_case():
    inp = replace(_minimal_feasible_inputs(), schedule_engine="pyomo")
    out = solve_schedule_pyomo(inp)
    assert not out.empty
    assert len(out) == 14
    assert set(out["station_key"].unique()) == {"S1"}
    per_day = out.groupby("ds").size()
    assert (per_day == 2).all()
    g = out.groupby(["ds", "employee_id"]).size()
    assert (g == 1).all()
