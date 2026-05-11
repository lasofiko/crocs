from __future__ import annotations

import pandas as pd

from crocs.services.labormap_service import apply_min_employees_per_station


def test_apply_min_employees_per_station() -> None:
    df = pd.DataFrame(
        {
            "ds": pd.date_range("2026-01-01", periods=2, freq="D"),
            "sale_hour": [10, 10],
            "station_key": ["A", "A"],
            "required_employees": [0, 1],
        },
    )
    out = apply_min_employees_per_station(df, 2)
    assert list(out["required_employees"]) == [2, 2]


def test_apply_min_relaxed_sale_hour_uses_floor_one() -> None:
    df = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-01-01")] * 2,
            "sale_hour": [10, 23],
            "station_key": ["A", "A"],
            "required_employees": [0, 0],
        },
    )
    out = apply_min_employees_per_station(df, 2, relaxed_sale_hours=frozenset({23}))
    assert int(out.loc[out["sale_hour"] == 10, "required_employees"].iloc[0]) == 2
    assert int(out.loc[out["sale_hour"] == 23, "required_employees"].iloc[0]) == 1


def test_apply_min_zero_noop() -> None:
    df = pd.DataFrame({"required_employees": [1]})
    out = apply_min_employees_per_station(df, 0)
    assert int(out["required_employees"].iloc[0]) == 1
