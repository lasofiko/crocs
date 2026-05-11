"""MILP через PuLP: базовый кейс как у CP-SAT."""

from __future__ import annotations

from dataclasses import replace

import pytest

pytest.importorskip("pulp", reason="pulp not installed")

import pulp

from crocs.services.schedule_pulp import solve_schedule_pulp
from tests.test_schedule_cp_sat import _minimal_feasible_inputs


def _any_pulp_solver() -> bool:
    try:
        if bool(pulp.HiGHS_CMD(msg=False).available()):
            return True
    except Exception:
        pass
    try:
        if bool(pulp.PULP_CBC_CMD(msg=False).available()):
            return True
    except Exception:
        pass
    return False


@pytest.mark.skipif(not _any_pulp_solver(), reason="no CBC/HiGHS available for PuLP")
def test_pulp_matches_cp_sat_shape_on_minimal_case():
    inp = replace(_minimal_feasible_inputs(), schedule_engine="pulp")
    out = solve_schedule_pulp(inp)
    assert not out.empty
    assert len(out) == 14
    assert set(out["station_key"].unique()) == {"S1"}
    per_day = out.groupby("ds").size()
    assert (per_day == 2).all()
    g = out.groupby(["ds", "employee_id"]).size()
    assert (g == 1).all()
