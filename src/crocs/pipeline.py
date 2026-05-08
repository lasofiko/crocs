from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from crocs.demand.guests_to_labor import build_hourly_demand
from crocs.forecast.predict import run_forecast
from crocs.io.loaders import RawDataBundle, load_raw_bundle, require_bundle
from crocs.io.writers import write_forecast_xlsx, write_schedule_xlsx
from crocs.quality.validate import validate_schedule
from crocs.scheduling.solve import SchedulingInputs, solve_schedule
from crocs.viz.plots import plot_placeholder_note


@dataclass
class PipelineResult:
    forecast: pd.DataFrame
    schedule: pd.DataFrame
    warnings: list[str]


def run_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    strict_inputs: bool = True,
) -> PipelineResult:
    """
    Полный прогон: load → forecast → demand → schedule → validate → export.
    Пока доменные шаги не реализованы, упадёт на NotImplementedError — это ожидаемо.
    """
    bundle = load_raw_bundle(data_dir)
    if strict_inputs:
        require_bundle(bundle)

    assert bundle.train is not None
    forecast_df = run_forecast(bundle.train)

    assert bundle.reqlabor is not None
    demand_df = build_hourly_demand(forecast_df, bundle.reqlabor)

    assert bundle.sched is not None
    assert bundle.station_priorities is not None
    assert bundle.shifts is not None
    assert bundle.staff_limits is not None

    schedule_df = solve_schedule(
        SchedulingInputs(
            hourly_demand=demand_df,
            sched=bundle.sched,
            station_priorities=bundle.station_priorities,
            shifts=bundle.shifts,
            staff_limits=bundle.staff_limits,
        )
    )

    violations = validate_schedule(
        schedule_df,
        staff_limits=bundle.staff_limits,
        sched=bundle.sched,
    )

    write_forecast_xlsx(forecast_df, output_dir / "forecast.xlsx")
    write_schedule_xlsx(schedule_df, output_dir / "schedule.xlsx")
    plot_placeholder_note(output_dir / "figures")

    warnings = violations.copy()
    return PipelineResult(forecast=forecast_df, schedule=schedule_df, warnings=warnings)


def load_bundle_only(data_dir: Path) -> RawDataBundle:
    """Только загрузка CSV (для отладки без полного прогона)."""
    return load_raw_bundle(data_dir)


def check_raw_present(data_dir: Path) -> None:
    """Бросает DataValidationError, если не хватает файлов."""
    require_bundle(load_raw_bundle(data_dir))
