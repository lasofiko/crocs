import pandas as pd

from crocs.domain.models import SchedulingInputs
from crocs.services.schedule_cp_sat import solve_schedule_cp_sat


def _minimal_feasible_inputs() -> SchedulingInputs:
    days = pd.date_range("2026-04-27", periods=7, freq="D")
    rows: list[dict] = []
    for d in days:
        rows.append(
            {
                "ds": d,
                "sale_hour": 12,
                "station_key": "S1",
                "required_employees": 1,
            }
        )
    hourly = pd.DataFrame(rows)

    sched_rows: list[dict] = []
    for e in (1, 2, 3):
        for wd in range(1, 8):
            sched_rows.append(
                {
                    "employee_id": e,
                    "day": wd,
                    "starttime": 7,
                    "finishtime": 23,
                }
            )
    sched = pd.DataFrame(sched_rows)
    sp = pd.DataFrame([{"station_key": "S1", "priority": 1}])
    shifts = pd.DataFrame([{"shift_duration": 5, "shift_priority": 1}])
    staff = pd.DataFrame(
        [
            {"employee_id": 1, "worktime_limit": 40, "shift_limit": 12},
            {"employee_id": 2, "worktime_limit": 40, "shift_limit": 12},
            {"employee_id": 3, "worktime_limit": 40, "shift_limit": 12},
        ]
    )
    return SchedulingInputs(
        hourly_demand=hourly,
        sched=sched,
        station_priorities=sp,
        shifts=shifts,
        staff_limits=staff,
        max_extra_coverage=2,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
        solver_time_limit_seconds=30.0,
    )


def test_cp_sat_produces_two_shifts_per_day_with_min_station_staff():
    """При min_employees_per_station=2 на каждый слот нужно два человека (по умолчанию)."""
    out = solve_schedule_cp_sat(_minimal_feasible_inputs())
    assert not out.empty
    assert len(out) == 14
    assert set(out["station_key"].unique()) == {"S1"}
    per_day = out.groupby("ds").size()
    assert (per_day == 2).all()


def test_one_shift_per_employee_per_day():
    out = solve_schedule_cp_sat(_minimal_feasible_inputs())
    g = out.groupby(["ds", "employee_id"]).size()
    assert (g == 1).all()
