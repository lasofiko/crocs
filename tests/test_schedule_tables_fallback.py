from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.io.csv_repository import load_schedule_optimization_tables


def test_schedule_tables_primary_then_fallback(tmp_path: Path) -> None:
    out = tmp_path / "output"
    raw = tmp_path / "raw"
    out.mkdir()
    raw.mkdir()
    pd.DataFrame({"x": [1]}).to_csv(raw / "sched.csv", index=False)
    pd.DataFrame({"y": [1]}).to_csv(raw / "station_priorities.csv", index=False)
    pd.DataFrame({"z": [1]}).to_csv(raw / "shifts.csv", index=False)
    pd.DataFrame({"w": [1]}).to_csv(raw / "staff_limits.csv", index=False)

    s, sp, sh, sl = load_schedule_optimization_tables(out, fallback_dir=raw)
    assert s is not None and sp is not None and sh is not None and sl is not None

    pd.DataFrame({"p": [2]}).to_csv(out / "sched.csv", index=False)
    s2, *_ = load_schedule_optimization_tables(out, fallback_dir=raw)
    assert s2 is not None
    assert int(s2["p"].iloc[0]) == 2
