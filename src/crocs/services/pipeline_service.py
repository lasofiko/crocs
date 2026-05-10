from __future__ import annotations

from pathlib import Path

from crocs.config import load_settings
from crocs.domain.models import PipelineResult, SchedulingInputs
from crocs.io.csv_repository import load_raw_bundle, require_bundle
from crocs.io.excel_repository import write_forecast_xlsx, write_schedule_xlsx
from crocs.services.forecast_service import run_forecast
from crocs.services.labormap_service import apply_min_employees_per_station, build_hourly_demand
from crocs.services.schedule_service import solve_schedule
from crocs.services.validate_service import validate_schedule
from crocs.viz.report_figures import write_pipeline_figures


def check_raw_present(data_dir: Path) -> None:
    require_bundle(load_raw_bundle(data_dir))


def run_pipeline(
    data_dir: Path,
    artifacts_dir: Path,
    *,
    strict_inputs: bool = True,
    config_path: Path | None = None,
) -> PipelineResult:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    bundle = load_raw_bundle(data_dir)
    if strict_inputs:
        require_bundle(bundle)

    assert bundle.train is not None
    forecast_df = run_forecast(
        bundle.train,
        forecast_start=settings.forecast.start,
        forecast_end=settings.forecast.end,
        open_hour=settings.forecast.open_hour,
        close_hour=settings.forecast.close_hour,
        weather=bundle.weather,
    )

    assert bundle.reqlabor is not None
    demand_df = build_hourly_demand(forecast_df, bundle.reqlabor)
    demand_df = apply_min_employees_per_station(
        demand_df,
        settings.scheduling.min_employees_per_station,
    )

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
            max_extra_coverage=settings.scheduling.max_extra_coverage,
            min_employees_per_station=settings.scheduling.min_employees_per_station,
            max_shifts_per_employee_week=settings.scheduling.max_shifts_per_employee_week,
            restaurant_open_hour=settings.forecast.open_hour,
            restaurant_close_hour=settings.forecast.close_hour,
            solver_time_limit_seconds=settings.scheduling.solver_time_limit_seconds,
        )
    )

    warnings = validate_schedule(schedule_df, bundle.staff_limits, bundle.sched, bundle.shifts)

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    write_forecast_xlsx(forecast_df, artifacts_dir / "forecast.xlsx")
    write_schedule_xlsx(schedule_df, artifacts_dir / "schedule.xlsx")

    figures_dir = artifacts_dir / "figures"
    try:
        write_pipeline_figures(
            forecast_df,
            schedule_df,
            demand_df,
            figures_dir,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
    except Exception as exc:
        warnings.append(f"графики не сохранены: {exc}")

    return PipelineResult(forecast=forecast_df, schedule=schedule_df, warnings=warnings)
