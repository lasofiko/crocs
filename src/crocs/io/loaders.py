from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from crocs.exceptions import DataValidationError


def load_csv_if_exists(path: Path, **read_kw) -> Optional[pd.DataFrame]:
    if not path.is_file():
        return None
    return pd.read_csv(path, **read_kw)


def load_excel_if_exists(
    path: Path,
    *,
    sheet_name: int | str = 0,
    **read_kw,
) -> Optional[pd.DataFrame]:
    if not path.is_file():
        return None
    return pd.read_excel(path, sheet_name=sheet_name, **read_kw)


def load_table_if_exists(
    data_dir: Path,
    stem: str,
    *,
    sheet_name: int | str = 0,
) -> Optional[pd.DataFrame]:
    """
    Одна логическая таблица: сначала ищем ``{stem}.csv``, затем ``{stem}.xlsx``.
    Для Excel по умолчанию первый лист (``sheet_name=0``); при нескольких листах
    передайте имя листа или индекс в вызове ``load_raw_bundle`` через расширение ниже.
    """
    csv_path = data_dir / f"{stem}.csv"
    if csv_path.is_file():
        return pd.read_csv(csv_path)
    xlsx_path = data_dir / f"{stem}.xlsx"
    if xlsx_path.is_file():
        return pd.read_excel(xlsx_path, sheet_name=sheet_name)
    return None


@dataclass
class RawDataBundle:
    train: Optional[pd.DataFrame]
    reqlabor: Optional[pd.DataFrame]
    sched: Optional[pd.DataFrame]
    station_priorities: Optional[pd.DataFrame]
    shifts: Optional[pd.DataFrame]
    staff_limits: Optional[pd.DataFrame]


def load_raw_bundle(data_dir: Path) -> RawDataBundle:
    """Загружает таблицы из data/raw: для каждой сущности допустимы .csv или .xlsx."""
    return RawDataBundle(
        train=load_table_if_exists(data_dir, "train"),
        reqlabor=load_table_if_exists(data_dir, "reqlabor"),
        sched=load_table_if_exists(data_dir, "sched"),
        station_priorities=load_table_if_exists(data_dir, "station_priorities"),
        shifts=load_table_if_exists(data_dir, "shifts"),
        staff_limits=load_table_if_exists(data_dir, "staff_limits"),
    )


def require_bundle(bundle: RawDataBundle) -> None:
    """Проверка, что все таблицы на месте (перед полным прогоном)."""
    missing = []
    if bundle.train is None:
        missing.append("train.csv или train.xlsx")
    if bundle.reqlabor is None:
        missing.append("reqlabor.csv или reqlabor.xlsx")
    if bundle.sched is None:
        missing.append("sched.csv или sched.xlsx")
    if bundle.station_priorities is None:
        missing.append("station_priorities.csv или station_priorities.xlsx")
    if bundle.shifts is None:
        missing.append("shifts.csv или shifts.xlsx")
    if bundle.staff_limits is None:
        missing.append("staff_limits.csv или staff_limits.xlsx")
    if missing:
        raise DataValidationError(
            "Отсутствуют файлы в data/raw: " + ", ".join(missing)
        )
