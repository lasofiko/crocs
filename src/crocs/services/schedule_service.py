from __future__ import annotations

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_cp_sat import solve_schedule_cp_sat
from crocs.services.schedule_pyomo import solve_schedule_pyomo
from crocs.services.staffing_recommendations import staffing_shortfall_hints


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    engine = (inputs.schedule_engine or "cp_sat").strip().lower()
    try:
        if engine == "pyomo":
            return solve_schedule_pyomo(inputs)
        if engine == "cp_sat":
            return solve_schedule_cp_sat(inputs)
        raise ScheduleError(
            f"Неизвестный scheduling.schedule_engine={inputs.schedule_engine!r}; "
            "ожидается cp_sat или pyomo.",
        )
    except ScheduleError as exc:
        hints = staffing_shortfall_hints(inputs)
        if hints:
            block = "\n".join(f"  • {line}" for line in hints)
            raise ScheduleError(
                f"{exc}\n\nПодсказки по доступности (можно расширить sched по образцу другого дня):\n{block}",
            ) from exc
        raise
