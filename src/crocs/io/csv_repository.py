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
    weather = _load_table(data_dir, "weather_moscow_open_meteo_forecast")
    if weather is None:
        weather = _load_table(data_dir, "weather_moscow")
    if weather is None:
        weather = _load_table(data_dir, "weather")
    return RawDataBundle(
        train=_load_table(data_dir, "train"),
        weather=weather,
        reqlabor=_load_table(data_dir, "reqlabor"),
        sched=_load_table(data_dir, "sched"),
        staff_limits=_load_table(data_dir, "staff_limits"),
        station_priorities=_load_table(data_dir, "station_priorities"),
        shifts=_load_table(data_dir, "shifts"),
    )


def require_bundle(bundle: RawDataBundle) -> None:
    """Все таблицы для полного пайплайна (прогноз + спрос + расписание CP-SAT)."""
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
            "Нет входных таблиц: " + ", ".join(f"{x}.csv/.xlsx" for x in missing),
        )


def require_ml_forecast_tables(bundle: RawDataBundle) -> None:
    """Для CatBoost-прогноза нужен train (погода опционально в bundle)."""
    if bundle.train is None:
        raise DataValidationError("Нет train.csv/.xlsx в raw_data_dir для ML-прогноза.")


def require_schedule_tables(bundle: RawDataBundle) -> None:
    """Таблицы для построения расписания (CP-SAT)."""
    if bundle.reqlabor is None:
        raise DataValidationError("Нет reqlabor.csv/.xlsx в raw_data_dir для расписания.")
    if bundle.sched is None:
        raise DataValidationError("Нет sched.csv/.xlsx в raw_data_dir для расписания.")
    if bundle.staff_limits is None:
        raise DataValidationError("Нет staff_limits.csv/.xlsx в raw_data_dir для расписания.")
    if bundle.station_priorities is None:
        raise DataValidationError("Нет station_priorities.csv/.xlsx для расписания.")
    if bundle.shifts is None:
        raise DataValidationError("Нет shifts.csv/.xlsx для расписания.")
