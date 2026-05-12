from __future__ import annotations

import pandas as pd

from crocs.services.labormap_service import apply_min_employees_per_station, build_hourly_demand


def test_build_hourly_demand_ml_style() -> None:
    """Версия строки reqlabor подбирается по календарю и часу (будни/утр.)."""
    forecast = pd.DataFrame(
        {
            "sale_date": [pd.Timestamp("2026-04-27")],
            "sale_hour": [10],
            "guests_count": [25],
        }
    )
    reqlabor = pd.DataFrame(
        {
            "station_key": ["S1", "S1"],
            "version": ["будни/утр.", "будни/утр."],
            "guests_count": [30, 100],
            "reqlabor": [2, 5],
        }
    )
    out = build_hourly_demand(forecast, reqlabor)
    assert "required_employees" in out.columns
    assert int(out.loc[out["station_key"] == "S1", "required_employees"].iloc[0]) == 2


def test_apply_min_employees_per_station() -> None:
    d = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27")],
            "sale_hour": [22],
            "station_key": ["S1"],
            "required_employees": [1],
        }
    )
    out = apply_min_employees_per_station(
        d,
        2,
        relaxed_sale_hours=frozenset({22}),
    )
    assert int(out["required_employees"].iloc[0]) == 1
