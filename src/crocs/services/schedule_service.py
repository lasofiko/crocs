from __future__ import annotations

import pandas as pd

from crocs.domain.models import SchedulingInputs


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    raise NotImplementedError("CP-SAT → колонки ds, station_key, employee_id, starttime, finishtime")
