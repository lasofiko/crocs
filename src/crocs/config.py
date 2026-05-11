from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

FORECAST_START = date(2026, 4, 27)
FORECAST_END = date(2026, 5, 3)
RESTAURANT_OPEN_HOUR = 7
RESTAURANT_CLOSE_HOUR = 23


class ProjectConfig(BaseModel):
    name: str = "crocs"


class PathConfig(BaseModel):
    raw_data_dir: Path = Path("data/raw")
    output_dir: Path = Path("data/output")


class InputConfig(BaseModel):
    train: str = "train.csv"
    reqlabor: str = "reqlabor.csv"
    sched: str = "sched.csv"
    staff_limits: str = "staff_limits.csv"
    station_priorities: str = "station_priorities.csv"
    shifts: str = "shifts.csv"


class OutputConfig(BaseModel):
    forecast: str = "forecast.xlsx"
    schedule: str = "schedule.xlsx"
    labor_demand: str = "labor_demand.xlsx"
    coverage_report: str = "coverage_report.xlsx"


class ForecastConfig(BaseModel):
    start: date = FORECAST_START
    end: date = FORECAST_END
    open_hour: int = Field(default=RESTAURANT_OPEN_HOUR, ge=0, le=23)
    # Час закрытия (верхняя граница по времени); слоты sale_hour = open … close−1 (полуинтервал).
    close_hour: int = Field(default=RESTAURANT_CLOSE_HOUR, ge=1, le=24)


class SchedulingConfig(BaseModel):
    solver_time_limit_seconds: int | None = None
    max_extra_coverage: int = Field(default=2, ge=0)
    min_employees_per_station: int = Field(
        default=2,
        ge=0,
        description=(
            "Нижняя граница числа людей на станции в каждом слоте (день, час, station_key) "
            "на горизонте расписания; 0 — без принудительного минимума."
        ),
    )
    min_employees_relaxed_sale_hours: list[int] = Field(
        default_factory=list,
        description=(
            "Список sale_hour (0–23), где на станции достаточно минимум одного человека, "
            "даже если min_employees_per_station > 1 (например поздний слот)."
        ),
    )
    max_shifts_per_employee_week: int = Field(default=5, ge=1, le=7)
    require_one_shift_per_sched_employee: bool = Field(
        default=True,
        description=(
            "Если true — у каждого человека из sched.csv минимум одна смена за горизонт недели "
            "(при большом списке и малом спросе часто даёт INFEASIBLE)."
        ),
    )

    @field_validator("min_employees_relaxed_sale_hours", mode="after")
    @classmethod
    def _normalize_relaxed_sale_hours(cls, v: list[int]) -> list[int]:
        seen: set[int] = set()
        out: list[int] = []
        for x in v:
            h = int(x)
            if 0 <= h <= 23 and h not in seen:
                seen.add(h)
                out.append(h)
        return sorted(out)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CROCS_", env_nested_delimiter="__")

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    inputs: InputConfig = Field(default_factory=InputConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)
    scheduling: SchedulingConfig = Field(default_factory=SchedulingConfig)


def load_settings(config_path: Path = Path("configs/default.yaml")) -> Settings:
    if not config_path.exists():
        return Settings()

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")

    return Settings.model_validate(raw)
