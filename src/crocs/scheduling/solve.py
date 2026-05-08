from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class SchedulingInputs:
    hourly_demand: pd.DataFrame
    sched: pd.DataFrame
    station_priorities: pd.DataFrame
    shifts: pd.DataFrame
    staff_limits: pd.DataFrame


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    """
    CP-SAT: назначение смен по станциям и времени с соблюдением ограничений ТЗ.
    Выход: колонки ds, station_key, employee_id, starttime, finishtime.
    """
    raise NotImplementedError(
        "Реализуйте модель OR-Tools CP-SAT (constraints + objective)"
    )
