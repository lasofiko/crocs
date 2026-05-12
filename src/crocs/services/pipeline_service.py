from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd

from crocs.config import GuestsSource, load_settings
from crocs.domain.models import PipelineResult
from crocs.exceptions import ScheduleError
from crocs.io.csv_repository import (
    load_raw_bundle,
    require_ml_forecast_tables,
    require_schedule_tables,
)
from crocs.io.excel_repository import (
    load_forecast_guests_xlsx,
    write_forecast_xlsx,
    write_schedule_xlsx,
    write_staffing_requirements_xlsx,
)
from crocs.services.forecast_service import run_forecast
from crocs.services.labormap_service import build_hourly_demand
from crocs.services.runtime_cache import (
    connect_redis,
    hourly_demand_cache_key,
    store_hourly_demand,
    try_load_hourly_demand,
)
from crocs.services.schedule_pulp import solve_schedule_pulp, staffing_requirements_table
from crocs.services.schedule_station_hour_tables import (
    build_daily_station_hour_tables,
    write_daily_station_hour_workbook,
)
from crocs.viz.report_figures import (
    plot_forecast_guests,
    plot_hourly_demand_by_station,
    plot_schedule_assigned_by_station,
    plot_schedule_gantt,
    plot_staffing_coverage,
    plot_total_demand_vs_assigned,
)


def _stage(msg: str) -> None:
    print(msg, flush=True)


def _reqlabor_mtime_ns(data_dir: Path) -> int | None:
    for name in ("reqlabor.csv", "reqlabor.xlsx"):
        p = data_dir / name
        if p.is_file():
            return int(p.stat().st_mtime_ns)
    return None


def check_raw_present(
    data_dir: Path,
    forecast_input_dir: Path | None = None,
    *,
    config_path: Path | None = None,
    guests_source: GuestsSource | None = None,
) -> None:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    fin_dir = (
        forecast_input_dir
        if forecast_input_dir is not None
        else settings.paths.forecast_input_dir
    )
    src: GuestsSource = (
        guests_source if guests_source is not None else settings.forecast.guests_source
    )
    bundle = load_raw_bundle(data_dir)
    if settings.schedule.enabled:
        require_schedule_tables(bundle)
    if src == "file":
        forecast_path = fin_dir / settings.outputs.forecast
        load_forecast_guests_xlsx(
            forecast_path,
            start=settings.forecast.start,
            end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
    else:
        require_ml_forecast_tables(bundle)


def run_pipeline(
    data_dir: Path,
    artifacts_dir: Path,
    *,
    strict_inputs: bool = True,
    config_path: Path | None = None,
    forecast_input_dir: Path | None = None,
    guests_source: GuestsSource | None = None,
) -> PipelineResult:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    fin_dir = (
        forecast_input_dir
        if forecast_input_dir is not None
        else settings.paths.forecast_input_dir
    )
    src: GuestsSource = (
        guests_source if guests_source is not None else settings.forecast.guests_source
    )
    rt = settings.runtime
    forecast_df: pd.DataFrame | None = None

    def _load_forecast_file() -> pd.DataFrame:
        fp = fin_dir / settings.outputs.forecast
        return load_forecast_guests_xlsx(
            fp,
            start=settings.forecast.start,
            end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )

    if rt.parallel_io_file_mode and src == "file":
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_b = ex.submit(load_raw_bundle, data_dir)
            fut_f = ex.submit(_load_forecast_file)
            bundle = fut_b.result()
            forecast_df = fut_f.result()
    else:
        bundle = load_raw_bundle(data_dir)

    if strict_inputs:
        if settings.schedule.enabled:
            require_schedule_tables(bundle)
        if src == "file":
            if forecast_df is None:
                forecast_df = _load_forecast_file()
        else:
            require_ml_forecast_tables(bundle)

    _stage(
        "Входные данные проверены "
        f"(прогноз гостей: {'файл в forecast_input_dir' if src == 'file' else 'модель по train'}).",
    )

    if src == "file":
        forecast_path = fin_dir / settings.outputs.forecast
        if forecast_df is None:
            _stage(f"Прогноз гостей из {forecast_path.resolve()} (без обучения модели)...")
            forecast_df = _load_forecast_file()
        else:
            _stage(f"Прогноз гостей из {forecast_path.resolve()} (уже в памяти)...")
    else:
        assert bundle.train is not None
        _stage("Прогноз гостей (CatBoost по train)...")
        forecast_df = run_forecast(
            bundle.train,
            forecast_start=settings.forecast.start,
            forecast_end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
            weather=bundle.weather,
        )
    _stage(f"Прогноз готов: {len(forecast_df)} строк.")

    warnings: list[str] = []
    hourly_demand_df = None
    schedule_df = None

    if settings.schedule.enabled:
        assert bundle.reqlabor is not None
        _stage("Почасовой спрос по станциям (reqlabor)...")
        rurl = (rt.redis_url or "").strip() or None
        rclient = connect_redis(rurl) if rt.cache_hourly_demand else None
        fp_forecast = (fin_dir / settings.outputs.forecast) if src == "file" else None
        ck = hourly_demand_cache_key(
            forecast_path=fp_forecast,
            reqlabor_mtime_ns=_reqlabor_mtime_ns(data_dir),
            morning_split_hour=settings.schedule.morning_split_hour,
            forecast_start=str(settings.forecast.start),
            forecast_end=str(settings.forecast.end),
        )
        if rt.cache_hourly_demand:
            hourly_demand_df = try_load_hourly_demand(
                redis_client=rclient,
                use_redis=rclient is not None,
                cache_dir=rt.hourly_demand_cache_dir,
                cache_key=ck,
            )
            if hourly_demand_df is not None:
                warnings.append("hourly_demand: loaded from cache (Redis or disk).")
        if hourly_demand_df is None:
            hourly_demand_df = build_hourly_demand(
                forecast_df,
                bundle.reqlabor,
                morning_split_hour=settings.schedule.morning_split_hour,
            )
            if rt.cache_hourly_demand:
                store_hourly_demand(
                    hourly_demand_df,
                    redis_client=rclient,
                    use_redis=rclient is not None,
                    cache_dir=rt.hourly_demand_cache_dir,
                    cache_key=ck,
                )
        req_export = staffing_requirements_table(
            hourly_demand_df,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
            min_staff_per_station=settings.schedule.min_staff_per_station,
            min_staff_only_when_demand=settings.schedule.min_staff_only_when_demand,
        )
        out_req = artifacts_dir / settings.outputs.staffing_requirements
        _stage(
            f"Запись {settings.outputs.staffing_requirements} "
            "(дата, час, станция, требуемое число работников)..."
        )
        write_staffing_requirements_xlsx(req_export, out_req)
        assert bundle.staff_limits is not None
        mode = settings.schedule.schedule_mode
        if mode == "station_hours":
            _stage("Schedule (PuLP): station_hours — hourly placement over horizon...")
        else:
            _stage("Schedule (PuLP): two_phase — day totals, then shifts and stations...")
        sch = settings.schedule
        _sched_kw = dict(
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
            shift_start_step_hours=sch.shift_start_step_hours,
            max_stations=sch.max_priority_stations,
            min_staff_per_station=sch.min_staff_per_station,
            min_staff_only_when_demand=sch.min_staff_only_when_demand,
            schedule_mode=sch.schedule_mode,
            min_shift_hours_per_employee=sch.min_shift_hours_per_employee,
            max_work_days_per_iso_week=sch.max_work_days_per_iso_week,
            max_hours_per_employee_day=sch.max_hours_per_employee_day,
            pulp_solver=sch.pulp_solver,
            pulp_time_limit_sec=sch.pulp_time_limit_sec,
            pulp_gap_rel=sch.pulp_gap_rel,
            pulp_cbc_threads=sch.pulp_cbc_threads,
            intraday_parallel_workers=sch.intraday_parallel_workers,
            intraday_sparse_station_hours=sch.intraday_sparse_station_hours,
            heartbeat_sec=sch.heartbeat_sec,
        )
        try:
            schedule_df = solve_schedule_pulp(
                hourly_demand_df,
                bundle.staff_limits,
                bundle.sched,
                bundle.station_priorities,
                allow_coverage_shortfall=sch.allow_coverage_shortfall,
                schedule_checkpoint_dir=(
                    rt.schedule_checkpoint_dir if rt.save_schedule_checkpoints else None
                ),
                **_sched_kw,
            )
        except ScheduleError as exc:
            if (
                sch.retry_schedule_with_coverage_shortfall
                and not sch.allow_coverage_shortfall
                and "Infeasible" in str(exc)
            ):
                warnings.append(
                    "Расписание: жёсткое покрытие дало Infeasible — повтор "
                    "allow_coverage_shortfall=true (сетка смен / одновременные станции)."
                )
                schedule_df = solve_schedule_pulp(
                    hourly_demand_df,
                    bundle.staff_limits,
                    bundle.sched,
                    bundle.station_priorities,
                    allow_coverage_shortfall=True,
                    schedule_checkpoint_dir=(
                        rt.schedule_checkpoint_dir if rt.save_schedule_checkpoints else None
                    ),
                    **_sched_kw,
                )
            else:
                raise

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_forecast = artifacts_dir / settings.outputs.forecast
    _stage(f"Запись {settings.outputs.forecast} в {artifacts_dir.resolve()}...")
    write_forecast_xlsx(forecast_df, out_forecast)

    if schedule_df is not None:
        out_sched = artifacts_dir / settings.outputs.schedule
        _stage(f"Запись {settings.outputs.schedule} в {artifacts_dir.resolve()}...")
        write_schedule_xlsx(schedule_df, out_sched)
        assert hourly_demand_df is not None
        hd_dates = hourly_demand_df.copy()
        hd_dates["sale_date"] = pd.to_datetime(hd_dates["sale_date"]).dt.date
        plan_days = sorted(hd_dates["sale_date"].unique())
        all_stations = sorted(hd_dates["station_key"].astype(str).unique())
        by_day = build_daily_station_hour_tables(
            schedule_df,
            days=plan_days,
            station_keys=all_stations,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
        out_by_day = artifacts_dir / settings.outputs.schedule_by_day
        _stage(f"Запись {settings.outputs.schedule_by_day} (листы по дням: станции x часы)...")
        write_daily_station_hour_workbook(out_by_day, by_day)

    figures_dir = artifacts_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    try:
        _stage("Графики (figures)...")
        plot_forecast_guests(forecast_df, figures_dir / "01_forecast_guests.png")
        if schedule_df is not None and not schedule_df.empty:
            gantt_dir = figures_dir / "02_schedule_gantt"
            cov_dir = figures_dir / "03_staffing_coverage"
            plot_schedule_gantt(schedule_df, gantt_dir / "gantt.png")
            assert hourly_demand_df is not None
            plot_staffing_coverage(
                hourly_demand_df,
                schedule_df,
                cov_dir / "coverage.png",
                min_staff_per_station=settings.schedule.min_staff_per_station,
                min_staff_only_when_demand=settings.schedule.min_staff_only_when_demand,
                open_hour=settings.forecast.open_hour,
                close_hour=settings.forecast.close_hour,
            )
        if hourly_demand_df is not None and not hourly_demand_df.empty:
            plot_hourly_demand_by_station(
                hourly_demand_df,
                figures_dir / "04_hourly_station_demand.png",
            )
        if schedule_df is not None and not schedule_df.empty:
            plot_schedule_assigned_by_station(
                schedule_df,
                figures_dir / "05_schedule_assigned_by_station.png",
            )
            if hourly_demand_df is not None and not hourly_demand_df.empty:
                plot_total_demand_vs_assigned(
                    hourly_demand_df,
                    schedule_df,
                    figures_dir / "06_total_demand_vs_assigned.png",
                )
    except Exception as exc:
        warnings.append(f"графики не сохранены: {exc}")

    return PipelineResult(
        forecast=forecast_df,
        warnings=warnings,
        hourly_demand=hourly_demand_df,
        schedule=schedule_df,
    )
