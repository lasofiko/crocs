from __future__ import annotations

import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.services.staffing_recommendations import staffing_shortfall_hints


def test_hints_suggest_second_employee_from_other_days() -> None:
    """Сотрудник 2 без понедельника в sched, но есть вт–вс — подсказка на пн."""
    days = pd.date_range("2026-04-27", periods=7, freq="D")
    hourly = pd.DataFrame(
        [
            {
                "ds": d,
                "sale_hour": 12,
                "station_key": "S1",
                "required_employees": 2,
            }
            for d in days
        ],
    )
    sched_rows: list[dict] = []
    for wd in range(1, 8):
        sched_rows.append({"employee_id": 1, "day": wd, "starttime": 7, "finishtime": 23})
    for wd in range(2, 8):
        sched_rows.append({"employee_id": 2, "day": wd, "starttime": 7, "finishtime": 23})
    sched = pd.DataFrame(sched_rows)
    sp = pd.DataFrame([{"station_key": "S1", "priority": 1}])
    shifts = pd.DataFrame([{"shift_duration": 5, "shift_priority": 1}])
    staff = pd.DataFrame(
        [
            {"employee_id": 1, "worktime_limit": 40, "shift_limit": 12},
            {"employee_id": 2, "worktime_limit": 40, "shift_limit": 12},
        ],
    )
    inp = SchedulingInputs(
        hourly_demand=hourly,
        sched=sched,
        station_priorities=sp,
        shifts=shifts,
        staff_limits=staff,
        min_employees_per_station=2,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    hints = staffing_shortfall_hints(inp, max_slots=5)
    joined = " ".join(hints)
    assert "пн" in joined or "понедельник" in joined.lower()
    assert "2" in joined or "2026-04-27" in joined
