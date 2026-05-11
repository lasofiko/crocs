from __future__ import annotations

import pandas as pd

from crocs.services.staffing_dashboard import build_staffing_grid


def test_staffing_grid_guests_assigned_and_employees() -> None:
    forecast = pd.DataFrame(
        [
            {"sale_date": "2026-05-01", "sale_hour": 10, "guests_count": 100},
            {"sale_date": "2026-05-01", "sale_hour": 11, "guests_count": 120},
        ]
    )
    labor = pd.DataFrame(
        [
            {"ds": pd.Timestamp("2026-05-01"), "sale_hour": 10, "station_key": "A", "required_employees": 2},
            {"ds": pd.Timestamp("2026-05-01"), "sale_hour": 10, "station_key": "B", "required_employees": 1},
            {"ds": pd.Timestamp("2026-05-01"), "sale_hour": 11, "station_key": "A", "required_employees": 3},
        ]
    )
    schedule = pd.DataFrame(
        [
            {
                "ds": "2026-05-01",
                "station_key": "A",
                "employee_id": "E1",
                "starttime": 9.0,
                "finishtime": 12.0,
            },
            {
                "ds": "2026-05-01",
                "station_key": "A",
                "employee_id": "E2",
                "starttime": 9.0,
                "finishtime": 12.0,
            },
        ]
    )
    out = build_staffing_grid(forecast, labor, schedule, open_hour=7, close_hour=23, warnings=[])
    by_key = {(r.date, r.sale_hour, r.station_key): r for r in out.rows}
    r_a10 = by_key[("2026-05-01", 10, "A")]
    assert r_a10.guests_forecast_total == 100
    assert r_a10.required_employees == 2
    assert r_a10.assigned_employees == 2
    assert set(r_a10.employee_ids) == {"E1", "E2"}
    assert r_a10.coverage_status == "ok"
    r_b10 = by_key[("2026-05-01", 10, "B")]
    assert r_b10.assigned_employees == 0
    assert r_b10.coverage_status == "vacant"
    r_a11 = by_key[("2026-05-01", 11, "A")]
    assert r_a11.guests_forecast_total == 120
    assert r_a11.required_employees == 3
    assert r_a11.assigned_employees == 2
    assert set(r_a11.employee_ids) == {"E1", "E2"}
    assert r_a11.coverage_status == "short"
    assert r_a11.coverage_gap == -1
