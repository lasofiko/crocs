from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.domain.models import RawDataBundle
from crocs.exceptions import DataValidationError


def _load_table(data_dir: Path, stem: str) -> pd.DataFrame | None:
    csv_path = data_dir / f"{stem}.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)
    return None


def load_raw_bundle(data_dir: Path) -> RawDataBundle:
    return RawDataBundle(
        train=_load_table(data_dir, "train"),
        reqlabor=_load_table(data_dir, "reqlabor"),
        sched=_load_table(data_dir, "sched"),
        station_priorities=_load_table(data_dir, "station_priorities"),
        shifts=_load_table(data_dir, "shifts"),
        staff_limits=_load_table(data_dir, "staff_limits"),
    )


def require_bundle(bundle: RawDataBundle) -> None:
    missing: list[str] = []
    if bundle.train is None:
        missing.append("train")
    if bundle.reqlabor is None:
        missing.append("reqlabor")
    if bundle.sched is None:
        missing.append("sched")
    if bundle.station_priorities is None:
        missing.append("station_priorities")
    if bundle.shifts is None:
        missing.append("shifts")
    if bundle.staff_limits is None:
        missing.append("staff_limits")
    if missing:
        raise DataValidationError(f"Missing CSV files in data/raw: {', '.join(missing)}")
