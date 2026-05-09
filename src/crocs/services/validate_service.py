from __future__ import annotations

import pandas as pd


def validate_schedule(
    schedule: pd.DataFrame,
    labor_demand: pd.DataFrame,
    staff_limits: pd.DataFrame,
    sched: pd.DataFrame,
    shifts: pd.DataFrame,
) -> pd.DataFrame:
    raise NotImplementedError("schedule validation -> coverage_report columns")
