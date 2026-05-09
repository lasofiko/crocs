from __future__ import annotations

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.services.schedule_cp_sat import solve_schedule_cp_sat


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    """CP-SAT shift scheduling via OR-Tools."""
    return solve_schedule_cp_sat(inputs)
