from __future__ import annotations

from pathlib import Path

import pandas as pd

from crocs.domain.models import RawDataBundle
from crocs.exceptions import DataValidationError


def _load_table(data_dir: Path, stem: str, *, sheet_name: int | str = 0) -> pd.DataFrame | None:
    csv_path = data_dir / f"{stem}.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)

    xlsx_path = data_dir / f"{stem}.xlsx"
    if xlsx_path.is_file():
        return pd.read_excel(xlsx_path, sheet_name=sheet_name)

    return None


def load_raw_bundle(data_dir: Path) -> RawDataBundle:
    weather = _load_table(data_dir, "weather_moscow")
    if weather is None:
        weather = _load_table(data_dir, "weather")
    return RawDataBundle(
        train=_load_table(data_dir, "train"),
        weather=weather,
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
        raise DataValidationError(
            "Нет входных таблиц: " + ", ".join(f"{x}.csv/.xlsx" for x in missing)
        )


def require_ml_forecast_tables(bundle: RawDataBundle) -> None:
    """Только train + reqlabor (и опционально weather) для прогноза и labor demand."""
    missing: list[str] = []
    if bundle.train is None:
        missing.append("train")
    if bundle.reqlabor is None:
        missing.append("reqlabor")
    if missing:
        raise DataValidationError(
            "Нет таблиц для ML/спроса в raw_data_dir: "
            + ", ".join(f"{x}.csv/.xlsx" for x in missing),
        )


def require_reqlabor_table(bundle: RawDataBundle) -> None:
    """Только reqlabor (для спроса по станциям при готовом прогнозе из файла)."""
    if bundle.reqlabor is None:
        raise DataValidationError(
            "Нет таблицы для спроса в raw_data_dir: reqlabor.csv/.xlsx",
        )


def _load_table_with_fallback(
    primary: Path,
    stem: str,
    *,
    fallback_dir: Path | None,
) -> pd.DataFrame | None:
    found = _load_table(primary, stem)
    if found is not None:
        return found
    if fallback_dir is not None and fallback_dir.resolve() != primary.resolve():
        return _load_table(fallback_dir, stem)
    return None


def load_schedule_optimization_tables(
    schedule_dir: Path,
    *,
    fallback_dir: Path | None = None,
) -> tuple[
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
    pd.DataFrame | None,
]:
    """Таблицы для солвера: сначала schedule_dir, при отсутствии файла — fallback_dir (часто data/raw)."""
    return (
        _load_table_with_fallback(schedule_dir, "sched", fallback_dir=fallback_dir),
        _load_table_with_fallback(schedule_dir, "station_priorities", fallback_dir=fallback_dir),
        _load_table_with_fallback(schedule_dir, "shifts", fallback_dir=fallback_dir),
        _load_table_with_fallback(schedule_dir, "staff_limits", fallback_dir=fallback_dir),
    )


def require_schedule_optimization_tables(
    schedule_dir: Path,
    *,
    fallback_dir: Path | None = None,
) -> None:
    sched, sp, sh, sl = load_schedule_optimization_tables(
        schedule_dir,
        fallback_dir=fallback_dir,
    )
    missing: list[str] = []
    if sched is None:
        missing.append("sched")
    if sp is None:
        missing.append("station_priorities")
    if sh is None:
        missing.append("shifts")
    if sl is None:
        missing.append("staff_limits")
    if missing:
        where = str(schedule_dir)
        if fallback_dir is not None and fallback_dir.resolve() != schedule_dir.resolve():
            where += f" и {fallback_dir}"
        raise DataValidationError(
            "Нет таблиц для оптимизации расписания (искали в "
            f"{where}): "
            + ", ".join(f"{x}.csv/.xlsx" for x in missing),
        )
