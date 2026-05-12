from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.io.schedule_db import (
    compute_schedule_cache_key,
    compute_schedule_inputs_fingerprint,
    persist_schedule_run,
    try_load_cached_schedule,
)


def test_persist_schedule_run_sqlite(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    sched = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27 08:00")],
            "station_key": ["A"],
            "employee_id": ["e1"],
            "starttime": [8.0],
            "finishtime": [10.0],
        }
    )
    ld = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27")],
            "sale_hour": [8],
            "station_key": ["A"],
            "required_employees": [2],
            "assigned_employees": [1],
        }
    )
    rid = persist_schedule_run(
        db,
        forecast_digest="abc",
        schedule_df=sched,
        labor_demand_df=ld,
        meta={"k": 1},
    )
    assert rid >= 1
    rid2 = persist_schedule_run(
        db,
        forecast_digest="def",
        schedule_df=sched,
        labor_demand_df=ld,
        meta={},
    )
    assert rid2 > rid


def test_schedule_cache_roundtrip(tmp_path: Path) -> None:
    from crocs.config import SchedulingConfig
    from crocs.domain.models import RawDataBundle

    db = tmp_path / "cache.db"
    sched = pd.DataFrame(
        {
            "ds": ["2026-04-27"],
            "station_key": ["A"],
            "employee_id": ["e1"],
            "starttime": [8.0],
            "finishtime": [10.0],
        }
    )
    ld = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27")],
            "sale_hour": [8],
            "station_key": ["A"],
            "required_employees": [2],
            "assigned_employees": [1],
        }
    )
    bundle = RawDataBundle(
        train=None,
        weather=None,
        reqlabor=pd.DataFrame({"a": [1]}),
        sched=pd.DataFrame({"b": [2]}),
        staff_limits=pd.DataFrame({"c": [3]}),
        station_priorities=pd.DataFrame({"d": [4]}),
        shifts=pd.DataFrame({"e": [5]}),
    )
    sch = SchedulingConfig()
    ck = compute_schedule_cache_key(
        forecast_digest="fx1",
        demand_df=ld,
        bundle=bundle,
        sch=sch,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    rid = persist_schedule_run(
        db,
        forecast_digest="fx1",
        schedule_df=sched,
        labor_demand_df=ld,
        cache_key=ck,
        meta={"test": True},
    )
    loaded = try_load_cached_schedule(db, ck)
    assert loaded is not None
    s2, d2, rid2 = loaded.schedule_df, loaded.labor_df, loaded.run_id
    assert loaded.match_kind == "exact"
    assert rid2 == rid
    assert len(s2) == 1
    assert len(d2) == 1
    assert int(d2.iloc[0]["sale_hour"]) == 8
    assert int(d2.iloc[0]["assigned_employees"]) == 1


def test_schedule_cache_inputs_fingerprint_reuse(tmp_path: Path) -> None:
    """Разный полный cache_key при тех же входах и структурных ограничениях — подхват из БД по inputs_fingerprint."""
    from crocs.config import SchedulingConfig
    from crocs.domain.models import RawDataBundle

    db = tmp_path / "relaxed_cache.db"
    sched = pd.DataFrame(
        {
            "ds": ["2026-04-27"],
            "station_key": ["A"],
            "employee_id": ["e1"],
            "starttime": [8.0],
            "finishtime": [10.0],
        }
    )
    ld = pd.DataFrame(
        {
            "ds": [pd.Timestamp("2026-04-27")],
            "sale_hour": [8],
            "station_key": ["A"],
            "required_employees": [2],
            "assigned_employees": [1],
        }
    )
    bundle = RawDataBundle(
        train=None,
        weather=None,
        reqlabor=pd.DataFrame({"a": [1]}),
        sched=pd.DataFrame({"b": [2]}),
        staff_limits=pd.DataFrame({"c": [3]}),
        station_priorities=pd.DataFrame({"d": [4]}),
        shifts=pd.DataFrame({"e": [5]}),
    )
    sch_a = SchedulingConfig(lns_iterations=10, solver_time_limit_seconds=60)
    sch_b = SchedulingConfig(lns_iterations=99, solver_time_limit_seconds=3600)
    digest = "fxsame"
    ifp = compute_schedule_inputs_fingerprint(
        forecast_digest=digest,
        demand_df=ld,
        bundle=bundle,
        sch=sch_a,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    ck_a = compute_schedule_cache_key(
        forecast_digest=digest,
        demand_df=ld,
        bundle=bundle,
        sch=sch_a,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    ck_b = compute_schedule_cache_key(
        forecast_digest=digest,
        demand_df=ld,
        bundle=bundle,
        sch=sch_b,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    assert ck_a != ck_b
    ifp_b = compute_schedule_inputs_fingerprint(
        forecast_digest=digest,
        demand_df=ld,
        bundle=bundle,
        sch=sch_b,
        restaurant_open_hour=7,
        restaurant_close_hour=23,
    )
    assert ifp == ifp_b

    rid = persist_schedule_run(
        db,
        forecast_digest=digest,
        schedule_df=sched,
        labor_demand_df=ld,
        cache_key=ck_a,
        inputs_fingerprint=ifp,
        meta={"test": True},
    )
    hit = try_load_cached_schedule(db, ck_b, inputs_fingerprint=ifp_b)
    assert hit is not None
    assert hit.run_id == rid
    assert hit.match_kind == "inputs_fingerprint"
