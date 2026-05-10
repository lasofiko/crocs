from __future__ import annotations

from crocs.domain.models import SchedulingInputs
from crocs.exceptions import ScheduleError
from crocs.services.schedule_cp_sat import solve_schedule_cp_sat
from crocs.services.staffing_recommendations import staffing_shortfall_hints


def solve_schedule(inputs: SchedulingInputs) -> pd.DataFrame:
    try:
        return solve_schedule_cp_sat(inputs)
    except ScheduleError as exc:
        hints = staffing_shortfall_hints(inputs)
        if hints:
            block = "\n".join(f"  • {line}" for line in hints)
            raise ScheduleError(
                f"{exc}\n\nПодсказки по доступности (можно расширить sched по образцу другого дня):\n{block}",
            ) from exc
        raise
