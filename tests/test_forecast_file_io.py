from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from crocs.exceptions import DataValidationError
from crocs.io.excel_repository import load_forecast_guests_xlsx


def test_load_forecast_guests_xlsx_filters_window(tmp_path: Path) -> None:
    path = tmp_path / "forecast.xlsx"
    df = pd.DataFrame(
        {
            "sale_date": pd.to_datetime(
                ["2026-04-26", "2026-04-27", "2026-04-27", "2026-05-04"],
            ),
            "sale_hour": [10, 7, 22, 10],
            "guests_count": [1.0, 2.0, 3.0, 9.0],
        }
    )
    df.to_excel(path, index=False)

    out = load_forecast_guests_xlsx(
        path,
        start=date(2026, 4, 27),
        end=date(2026, 5, 3),
        open_hour=7,
        close_hour=23,
    )
    assert len(out) == 2
    assert list(out["sale_hour"]) == [7, 22]
    assert list(out["guests_count"]) == [2, 3]


def test_load_forecast_guests_xlsx_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(path, index=False)
    with pytest.raises(DataValidationError, match="нужны колонки"):
        load_forecast_guests_xlsx(
            path,
            start=date(2026, 4, 27),
            end=date(2026, 5, 3),
            open_hour=7,
            close_hour=23,
        )
