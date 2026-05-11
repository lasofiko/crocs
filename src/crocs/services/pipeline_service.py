from __future__ import annotations

from pathlib import Path

from crocs.config import GuestsSource, load_settings
from crocs.domain.models import PipelineResult, SchedulingInputs
from crocs.io.csv_repository import (
    load_raw_bundle,
    load_schedule_optimization_tables,
    require_ml_forecast_tables,
    require_reqlabor_table,
    require_schedule_optimization_tables,
)
from crocs.io.excel_repository import (
    load_forecast_guests_xlsx,
    write_forecast_xlsx,
    write_schedule_staffing_by_hour_xlsx,
    write_schedule_xlsx,
)
from crocs.services.forecast_service import run_forecast
from crocs.services.labormap_service import apply_min_employees_per_station, build_hourly_demand
from crocs.services.schedule_service import solve_schedule
from crocs.services.validate_service import validate_schedule
from crocs.viz.report_figures import write_pipeline_figures


def _stage(msg: str) -> None:
    print(msg, flush=True)


def check_raw_present(
    data_dir: Path,
    schedule_input_dir: Path | None = None,
    *,
    config_path: Path | None = None,
    guests_source: GuestsSource | None = None,
) -> None:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    sched_dir = schedule_input_dir if schedule_input_dir is not None else settings.paths.schedule_input_dir
    src: GuestsSource = guests_source if guests_source is not None else settings.forecast.guests_source
    bundle = load_raw_bundle(data_dir)
    if src == "file":
        require_reqlabor_table(bundle)
        require_schedule_optimization_tables(sched_dir, fallback_dir=data_dir)
        forecast_path = sched_dir / settings.outputs.forecast
        load_forecast_guests_xlsx(
            forecast_path,
            start=settings.forecast.start,
            end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
    else:
        require_ml_forecast_tables(bundle)
        require_schedule_optimization_tables(sched_dir, fallback_dir=data_dir)


def run_pipeline(
    data_dir: Path,
    artifacts_dir: Path,
    *,
    strict_inputs: bool = True,
    config_path: Path | None = None,
    schedule_input_dir: Path | None = None,
    guests_source: GuestsSource | None = None,
) -> PipelineResult:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    sched_dir = schedule_input_dir if schedule_input_dir is not None else settings.paths.schedule_input_dir
    src: GuestsSource = guests_source if guests_source is not None else settings.forecast.guests_source

    bundle = load_raw_bundle(data_dir)
    sched_df, sp_df, sh_df, sl_df = load_schedule_optimization_tables(
        sched_dir,
        fallback_dir=data_dir,
    )
    if strict_inputs:
        if src == "file":
            require_reqlabor_table(bundle)
            require_schedule_optimization_tables(sched_dir, fallback_dir=data_dir)
        else:
            require_ml_forecast_tables(bundle)
            require_schedule_optimization_tables(sched_dir, fallback_dir=data_dir)
    _stage(
        "Входные таблицы загружены и проверены "
        f"(спрос: raw_data_dir; прогноз гостей: {'файл в schedule_input_dir' if src == 'file' else 'модель по train'}; "
        "расписание: сначала schedule_input_dir, при отсутствии файла — data_dir).",
    )

    if src == "file":
        forecast_path = sched_dir / settings.outputs.forecast
        _stage(f"Прогноз гостей из {forecast_path.resolve()} (без обучения модели)...")
        forecast_df = load_forecast_guests_xlsx(
            forecast_path,
            start=settings.forecast.start,
            end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
    else:
        assert bundle.train is not None
        _stage("Прогноз гостей (CatBoost по train) — обычно самый долгий шаг...")
        forecast_df = run_forecast(
            bundle.train,
            forecast_start=settings.forecast.start,
            forecast_end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
            weather=bundle.weather,
        )
    _stage(f"Прогноз готов: {len(forecast_df)} строк.")

    assert bundle.reqlabor is not None
    _stage("Потребность в персонале по часам и станциям...")
    demand_df = build_hourly_demand(forecast_df, bundle.reqlabor)
    relax_hours = frozenset(settings.scheduling.min_employees_relaxed_sale_hours)
    demand_df = apply_min_employees_per_station(
        demand_df,
        settings.scheduling.min_employees_per_station,
        relaxed_sale_hours=relax_hours,
    )

    assert sched_df is not None
    assert sp_df is not None
    assert sh_df is not None
    assert sl_df is not None

    _stage(
        f"Расписание ({settings.scheduling.schedule_engine}): подбор смен, может занять минуты...",
    )
    schedule_df = solve_schedule(
        SchedulingInputs(
            hourly_demand=demand_df,
            sched=sched_df,
            station_priorities=sp_df,
            shifts=sh_df,
            staff_limits=sl_df,
            max_extra_coverage=settings.scheduling.max_extra_coverage,
            min_employees_per_station=settings.scheduling.min_employees_per_station,
            min_employees_relaxed_sale_hours=tuple(settings.scheduling.min_employees_relaxed_sale_hours),
            max_shifts_per_employee_week=settings.scheduling.max_shifts_per_employee_week,
            require_one_shift_per_sched_employee=settings.scheduling.require_one_shift_per_sched_employee,
            restaurant_open_hour=settings.forecast.open_hour,
            restaurant_close_hour=settings.forecast.close_hour,
            solver_time_limit_seconds=settings.scheduling.solver_time_limit_seconds,
            schedule_engine=settings.scheduling.schedule_engine,
            milp_solver=settings.scheduling.milp_solver,
            coverage_understaff_penalty=settings.scheduling.coverage_understaff_penalty,
        )
    )
    _stage(f"Расписание построено: {len(schedule_df)} строк.")

    warnings = validate_schedule(
        schedule_df,
        sl_df,
        sched_df,
        sh_df,
        warn_unused_sched_roster=settings.scheduling.validation_warn_unused_sched_roster,
        warn_less_than_two_days_off=settings.scheduling.validation_warn_less_than_two_days_off,
    )

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    _stage(
        f"Запись forecast.xlsx, schedule.xlsx и {settings.outputs.schedule_staffing_by_hour} "
        f"в {artifacts_dir.resolve()}...",
    )
    write_forecast_xlsx(forecast_df, artifacts_dir / settings.outputs.forecast)
    write_schedule_xlsx(schedule_df, artifacts_dir / settings.outputs.schedule)
    write_schedule_staffing_by_hour_xlsx(
        schedule_df,
        demand_df,
        open_hour=settings.forecast.open_hour,
        close_hour=settings.forecast.close_hour,
        path=artifacts_dir / settings.outputs.schedule_staffing_by_hour,
    )

    figures_dir = artifacts_dir / "figures"
    try:
        _stage("Графики отчета...")
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

    return PipelineResult(
        forecast=forecast_df,
        schedule=schedule_df,
        labor_demand=demand_df,
        warnings=warnings,
    )
