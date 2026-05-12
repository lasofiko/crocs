from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from crocs.config import GuestsSource, load_settings
from crocs.domain.models import PipelineResult, SchedulingInputs
from crocs.io.csv_repository import (
    load_raw_bundle,
    require_bundle,
    require_ml_forecast_tables,
    require_schedule_tables,
)
from crocs.io.excel_repository import (
    load_forecast_guests_xlsx,
    write_coverage_report_xlsx,
    write_forecast_xlsx,
    write_labor_demand_xlsx,
    write_schedule_xlsx,
)
from crocs.io.schedule_db import (
    compute_schedule_cache_key,
    compute_schedule_inputs_fingerprint,
    persist_schedule_run,
    schedule_cache_debug_counts,
    try_load_cached_schedule,
)
from crocs.services.forecast_service import run_forecast
from crocs.services.labormap_service import apply_min_employees_per_station, build_hourly_demand
from crocs.services.schedule_service import solve_schedule
from crocs.services.staffing_dashboard import (
    build_staffing_grid,
    coverage_report_dataframe,
    enrich_labor_demand_with_assigned,
)
from crocs.services.validate_service import validate_schedule
from crocs.viz.report_figures import plot_forecast_guests, write_pipeline_figures


def _stage(msg: str) -> None:
    print(msg, flush=True)


def _forecast_digest(df: pd.DataFrame) -> str:
    blob = df.sort_values(list(df.columns)).to_csv(index=False).encode("utf-8", errors="replace")
    return hashlib.sha256(blob).hexdigest()[:24]


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
    if settings.scheduling.enabled:
        require_bundle(bundle)
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
    sch = settings.scheduling

    bundle = load_raw_bundle(data_dir)

    if strict_inputs:
        if sch.enabled:
            require_bundle(bundle)
        elif src == "file":
            load_forecast_guests_xlsx(
                fin_dir / settings.outputs.forecast,
                start=settings.forecast.start,
                end=settings.forecast.end,
                open_hour=settings.forecast.open_hour,
                close_hour=settings.forecast.close_hour,
            )
        else:
            require_ml_forecast_tables(bundle)

    _stage(
        "Входные данные проверены "
        f"(прогноз гостей: {'файл в forecast_input_dir' if src == 'file' else 'модель по train'}).",
    )

    if src == "file":
        forecast_path = fin_dir / settings.outputs.forecast
        _stage(f"Прогноз гостей из {forecast_path.resolve()}...")
        forecast_df = load_forecast_guests_xlsx(
            forecast_path,
            start=settings.forecast.start,
            end=settings.forecast.end,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
        )
    else:
        assert bundle.train is not None
        _stage("Прогноз гостей (модель по train)...")
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
    schedule_df: pd.DataFrame | None = None
    demand_df: pd.DataFrame | None = None
    schedule_from_db = False
    digest_fc = ""
    cache_key: str | None = None
    inputs_fp: str | None = None

    if sch.enabled:
        assert bundle.reqlabor is not None
        require_schedule_tables(bundle)
        _stage("Потребность в персонале по часам и станциям (reqlabor)...")
        demand_df = build_hourly_demand(forecast_df, bundle.reqlabor)
        relax_hours = frozenset(sch.min_employees_relaxed_sale_hours)
        demand_df = apply_min_employees_per_station(
            demand_df,
            sch.min_employees_per_station,
            relaxed_sale_hours=relax_hours,
        )

        assert bundle.sched is not None
        assert bundle.station_priorities is not None
        assert bundle.shifts is not None
        assert bundle.staff_limits is not None

        digest_fc = _forecast_digest(forecast_df)
        inputs_fp = compute_schedule_inputs_fingerprint(
            forecast_digest=digest_fc,
            demand_df=demand_df,
            bundle=bundle,
            sch=sch,
            restaurant_open_hour=settings.forecast.open_hour,
            restaurant_close_hour=settings.forecast.close_hour,
        )
        dbp = rt.schedule_db_path
        if dbp is not None:
            cache_key = compute_schedule_cache_key(
                forecast_digest=digest_fc,
                demand_df=demand_df,
                bundle=bundle,
                sch=sch,
                restaurant_open_hour=settings.forecast.open_hour,
                restaurant_close_hour=settings.forecast.close_hour,
            )
            if sch.schedule_cache_from_db:
                hit = try_load_cached_schedule(
                    dbp,
                    cache_key,
                    inputs_fingerprint=inputs_fp,
                )
                if hit is not None:
                    schedule_df = hit.schedule_df
                    demand_cached = hit.labor_df
                    rid = hit.run_id
                    if demand_cached is not None and not demand_cached.empty:
                        demand_df = demand_cached
                    schedule_from_db = True
                    kind_ru = "точное совпадение ключа" if hit.match_kind == "exact" else "совпадение входов (другой сценарий солвера)"
                    _stage(
                        f"Кэш SQLite: загружено из БД (run_id={rid}, {kind_ru}), CP-SAT/LNS пропускаются.",
                    )
                    if hit.match_kind == "exact":
                        warnings.append(
                            f"schedule_cache: расписание и спрос из БД (run_id={rid}), CP-SAT/LNS не вызывались.",
                        )
                    else:
                        warnings.append(
                            f"schedule_cache: расписание и спрос из БД по совпадению входов (run_id={rid}), "
                            "сценарий солвера/LNS в YAML отличался от сохранённого прогона — CP-SAT/LNS не вызывались.",
                        )
                else:
                    if not dbp.is_file():
                        _stage(
                            f"Кэш SQLite: файла БД ещё нет ({dbp.resolve()}) — после успешного прогона появится кэш.",
                        )
                        warnings.append(
                            f"schedule_cache: файла БД ещё нет ({dbp.resolve()}) — после первого успешного прогона с записью в БД появится кэш.",
                        )
                    else:
                        total_runs, with_slots = schedule_cache_debug_counts(dbp)
                        _stage(
                            f"Кэш SQLite: промах (БД {dbp.resolve()}, прогонов={total_runs}, с сменами={with_slots}). "
                            "Будет CP-SAT/LNS. Если прогонов больше чем «с сменами» — в БД были «пустые» записи (старый баг); "
                            "сейчас сохранение атомарное.",
                        )
                        warnings.append(
                            "schedule_cache: промах — нет run ни по полному cache_key, ни по отпечатку входов "
                            "(inputs_fingerprint): изменились прогноз, сырьё, спрос, структурные ограничения scheduling "
                            "или часы ресторана; либо в SQLite ещё не было успешного сохранения.",
                        )

        if not schedule_from_db:
            _stage("Расписание (CP-SAT + LNS): подбор смен, может занять минуты...")
            schedule_df = solve_schedule(
                SchedulingInputs(
                    hourly_demand=demand_df,
                    sched=bundle.sched,
                    station_priorities=bundle.station_priorities,
                    shifts=bundle.shifts,
                    staff_limits=bundle.staff_limits,
                    max_extra_coverage=sch.max_extra_coverage,
                    min_employees_per_station=sch.min_employees_per_station,
                    min_employees_relaxed_sale_hours=tuple(sch.min_employees_relaxed_sale_hours),
                    max_shifts_per_employee_week=sch.max_shifts_per_employee_week,
                    require_one_shift_per_sched_employee=sch.require_one_shift_per_sched_employee,
                    restaurant_open_hour=settings.forecast.open_hour,
                    restaurant_close_hour=settings.forecast.close_hour,
                    solver_time_limit_seconds=sch.solver_time_limit_seconds,
                    cp_sat_stop_after_first_solution=sch.cp_sat_stop_after_first_solution,
                    lns_enabled=sch.lns_enabled,
                    lns_iterations=sch.lns_iterations,
                    lns_repair_seconds=sch.lns_repair_seconds,
                    lns_destroy_days_min=sch.lns_destroy_days_min,
                    lns_destroy_days_max=sch.lns_destroy_days_max,
                    lns_staff_destroy_fraction=sch.lns_staff_destroy_fraction,
                    lns_seed=sch.lns_seed,
                )
            )
        _stage(f"Расписание построено: {len(schedule_df)} строк.")
        warnings.extend(
            validate_schedule(schedule_df, bundle.staff_limits, bundle.sched, bundle.shifts)
        )

    if demand_df is not None and not demand_df.empty:
        if schedule_df is not None and not schedule_df.empty:
            demand_df = enrich_labor_demand_with_assigned(
                demand_df,
                schedule_df,
                open_hour=settings.forecast.open_hour,
                close_hour=settings.forecast.close_hour,
            )
        elif "assigned_employees" not in demand_df.columns:
            demand_df = demand_df.copy()
            demand_df["assigned_employees"] = 0

    dbp = rt.schedule_db_path
    if (
        sch.enabled
        and not schedule_from_db
        and schedule_df is not None
        and not schedule_df.empty
        and dbp is not None
        and cache_key is not None
    ):
        try:
            rid = persist_schedule_run(
                dbp,
                forecast_digest=digest_fc,
                schedule_df=schedule_df,
                labor_demand_df=demand_df,
                cache_key=cache_key,
                inputs_fingerprint=inputs_fp,
                meta={
                    "guests_source": src,
                    "schedule_solver": "cp_sat_lns" if sch.lns_enabled else "cp_sat",
                    "forecast_rows": len(forecast_df),
                    "schedule_rows": len(schedule_df),
                    "labor_demand_rows": len(demand_df) if demand_df is not None else 0,
                    "from_db_cache": False,
                },
            )
            warnings.append(
                f"schedule_db: сохранён прогон run_id={rid} в {dbp.resolve()} (до экспорта xlsx — кэш не теряется при блокировке файлов).",
            )
        except Exception as exc:
            warnings.append(f"schedule_db: не удалось записать: {exc}")

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_forecast = artifacts_dir / settings.outputs.forecast
    _stage(f"Запись {settings.outputs.forecast} в {artifacts_dir.resolve()}...")
    write_forecast_xlsx(forecast_df, out_forecast)

    if demand_df is not None and not demand_df.empty:
        out_ld = artifacts_dir / settings.outputs.labor_demand
        _stage(f"Запись {settings.outputs.labor_demand}...")
        write_labor_demand_xlsx(demand_df, out_ld)

    if schedule_df is not None:
        out_sched = artifacts_dir / settings.outputs.schedule
        _stage(f"Запись {settings.outputs.schedule}...")
        write_schedule_xlsx(schedule_df, out_sched)

        grid = build_staffing_grid(
            forecast_df,
            demand_df,
            schedule_df,
            open_hour=settings.forecast.open_hour,
            close_hour=settings.forecast.close_hour,
            warnings=warnings,
        )
        warnings.extend(grid.warnings)
        cov_df = coverage_report_dataframe(grid)
        out_cov = artifacts_dir / settings.outputs.coverage_report
        _stage(f"Запись {settings.outputs.coverage_report}...")
        write_coverage_report_xlsx(cov_df, out_cov)

    figures_dir = artifacts_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)
    try:
        _stage("Графики (figures)...")
        plot_forecast_guests(forecast_df, figures_dir / "01_forecast_guests.png")
        if schedule_df is not None and demand_df is not None and not schedule_df.empty:
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
        warnings=warnings,
        schedule=schedule_df,
        labor_demand=demand_df,
    )
