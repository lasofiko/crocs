from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal

GuestsSource = Literal["model", "file"]

import yaml
from pydantic import BaseModel, Field
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
    # Готовый forecast.xlsx при guests_source=file (часто совпадает с output_dir).
    forecast_input_dir: Path = Path("data/output")


class InputConfig(BaseModel):
    train: str = "train.csv"
    reqlabor: str = "reqlabor.csv"


class OutputConfig(BaseModel):
    forecast: str = "forecast.xlsx"


class ForecastConfig(BaseModel):
    start: date = FORECAST_START
    end: date = FORECAST_END
    open_hour: int = Field(default=RESTAURANT_OPEN_HOUR, ge=0, le=23)
    close_hour: int = Field(default=RESTAURANT_CLOSE_HOUR, ge=1, le=24)
    guests_source: GuestsSource = Field(
        default="model",
        description=(
            "model — CatBoost по train из raw_data_dir; "
            "file — готовый прогноз из forecast_input_dir / outputs.forecast."
        ),
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="CROCS_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    paths: PathConfig = Field(default_factory=PathConfig)
    inputs: InputConfig = Field(default_factory=InputConfig)
    outputs: OutputConfig = Field(default_factory=OutputConfig)
    forecast: ForecastConfig = Field(default_factory=ForecastConfig)


def load_settings(config_path: Path = Path("configs/default.yaml")) -> Settings:
    if not config_path.exists():
        return Settings()

    with config_path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file) or {}

    if not isinstance(raw, dict):
        raise ValueError(f"Config must be a mapping: {config_path}")

    paths_raw = raw.get("paths")
    if isinstance(paths_raw, dict):
        merged_paths = dict(paths_raw)
        if "forecast_input_dir" not in merged_paths and "schedule_input_dir" in merged_paths:
            merged_paths["forecast_input_dir"] = merged_paths["schedule_input_dir"]
        raw = {**raw, "paths": merged_paths}

    return Settings.model_validate(raw)
