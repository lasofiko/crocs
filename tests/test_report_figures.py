from pathlib import Path

import pandas as pd

from crocs.viz.report_figures import write_pipeline_figures


def test_write_pipeline_figures_smoke(tmp_path: Path) -> None:
    forecast = pd.DataFrame(
        {
            "sale_date": ["2026-04-27", "2026-04-27"],
            "sale_hour": [7, 8],
            "guests_count": [10, 20],
        }
    )
    demand = pd.DataFrame(
        {
            "ds": pd.to_datetime(["2026-04-27", "2026-04-27"]),
            "sale_hour": [7, 8],
            "station_key": ["S1", "S1"],
            "required_employees": [1, 2],
        }
    )
    schedule = pd.DataFrame(
        {
            "ds": ["2026-04-27"],
            "station_key": ["S1"],
            "employee_id": [1],
            "starttime": [7.0],
            "finishtime": [15.0],
        }
    )
    out = tmp_path / "figs"
    write_pipeline_figures(forecast, schedule, demand, out, open_hour=7, close_hour=23)
    assert (out / "01_forecast_guests.png").is_file()
    assert any((out / "02_schedule_gantt").glob("*.png"))
    assert any((out / "03_staffing_coverage").glob("*.png"))
