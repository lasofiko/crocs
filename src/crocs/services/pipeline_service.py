from __future__ import annotations

from pathlib import Path

from crocs.config import Settings
from crocs.domain.models import PipelineResult, SchedulingInputs
from crocs.io.csv_repository import load_raw_bundle, require_bundle
from crocs.io.excel_repository import (
    write_coverage_report_xlsx,
    write_forecast_xlsx,
    write_labor_demand_xlsx,
    write_schedule_xlsx,
)
from crocs.services.forecast_service import run_forecast
from crocs.services.labormap_service import build_hourly_demand
from crocs.services.schedule_service import solve_schedule
from crocs.services.validate_service import validate_schedule


def run_pipeline(
    data_dir: Path,
    output_dir: Path,
    *,
    settings: Settings | None = None,
    strict_inputs: bool = True,
) -> PipelineResult:
    settings = settings or Settings()
    bundle = load_raw_bundle(data_dir)
    if strict_inputs:
        require_bundle(bundle)

    assert bundle.train is not None
    forecast_df = run_forecast(bundle.train)

    assert bundle.reqlabor is not None
    labor_demand_df = build_hourly_demand(forecast_df, bundle.reqlabor)

    assert bundle.sched is not None
    assert bundle.station_priorities is not None
    assert bundle.shifts is not None
    assert bundle.staff_limits is not None

    schedule_df = solve_schedule(
        SchedulingInputs(
            hourly_demand=labor_demand_df,
            sched=bundle.sched,
            station_priorities=bundle.station_priorities,
            shifts=bundle.shifts,
            staff_limits=bundle.staff_limits,
        )
    )

    coverage_report_df = validate_schedule(
        schedule_df,
        labor_demand_df,
        bundle.staff_limits,
        bundle.sched,
        bundle.shifts,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_forecast_xlsx(forecast_df, output_dir / settings.outputs.forecast)
    write_labor_demand_xlsx(labor_demand_df, output_dir / settings.outputs.labor_demand)
    write_schedule_xlsx(schedule_df, output_dir / settings.outputs.schedule)
    write_coverage_report_xlsx(coverage_report_df, output_dir / settings.outputs.coverage_report)

    return PipelineResult(
        forecast=forecast_df,
        labor_demand=labor_demand_df,
        schedule=schedule_df,
        coverage_report=coverage_report_df,
    )


def check_raw_present(data_dir: Path) -> None:
    require_bundle(load_raw_bundle(data_dir))
