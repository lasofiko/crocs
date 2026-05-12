from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.viz.report_figures import plot_forecast_guests, write_pipeline_figures


def test_plot_forecast_guests_writes_png(tmp_path: Path) -> None:
    fc = pd.DataFrame(
        {
            "sale_date": [pd.Timestamp("2026-04-27").date()],
            "sale_hour": [10],
            "guests_count": [12],
        }
    )
    path = tmp_path / "fc.png"
    plot_forecast_guests(fc, path)
    assert path.is_file() and path.stat().st_size > 100


def test_write_pipeline_figures_smoke(tmp_path: Path) -> None:
    fc = pd.DataFrame(
        {
            "sale_date": [pd.Timestamp("2026-04-27").date()] * 3,
            "sale_hour": [8, 9, 10],
            "guests_count": [5, 6, 7],
        }
    )
    ld = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27").normalize()] * 3,
            "sale_hour": [8, 9, 10],
            "station_key": ["A", "A", "A"],
            "required_employees": [2, 2, 2],
        }
    )
    sched = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27 08:00")] * 2,
            "station_key": ["A", "A"],
            "employee_id": ["e1", "e1"],
            "starttime": [8.0, 9.0],
            "finishtime": [9.0, 10.0],
        }
    )
    write_pipeline_figures(fc, sched, ld, tmp_path, open_hour=7, close_hour=12)
    assert (tmp_path / "02_schedule_gantt").exists() or (tmp_path / "03_staffing_coverage").exists()
