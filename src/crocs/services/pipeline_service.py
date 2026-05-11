from __future__ import annotations

from pathlib import Path

from crocs.config import GuestsSource, load_settings
from crocs.domain.models import PipelineResult
from crocs.io.csv_repository import load_raw_bundle, require_ml_forecast_tables
from crocs.io.excel_repository import load_forecast_guests_xlsx, write_forecast_xlsx
from crocs.services.forecast_service import run_forecast
from crocs.viz.report_figures import plot_forecast_guests


def _stage(msg: str) -> None:
    print(msg, flush=True)


def check_raw_present(
    data_dir: Path,
    forecast_input_dir: Path | None = None,
    *,
    config_path: Path | None = None,
    guests_source: GuestsSource | None = None,
) -> None:
    cfg = config_path if config_path is not None else Path("configs/default.yaml")
    settings = load_settings(cfg)
    fin_dir = forecast_input_dir if forecast_input_dir is not None else settings.paths.forecast_input_dir
    src: GuestsSource = guests_source if guests_source is not None else settings.forecast.guests_source
    bundle = load_raw_bundle(data_dir)
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
    fin_dir = forecast_input_dir if forecast_input_dir is not None else settings.paths.forecast_input_dir
    src: GuestsSource = guests_source if guests_source is not None else settings.forecast.guests_source

    bundle = load_raw_bundle(data_dir)
    if strict_inputs:
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

    _stage(
        "Входные данные проверены "
        f"(прогноз гостей: {'файл в forecast_input_dir' if src == 'file' else 'модель по train'}).",
    )

    if src == "file":
        forecast_path = fin_dir / settings.outputs.forecast
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

    artifacts_dir.mkdir(parents=True, exist_ok=True)
    out_forecast = artifacts_dir / settings.outputs.forecast
    _stage(f"Запись {settings.outputs.forecast} в {artifacts_dir.resolve()}...")
    write_forecast_xlsx(forecast_df, out_forecast)

    figures_dir = artifacts_dir / "figures"
    try:
        _stage("График прогноза...")
        figures_dir.mkdir(parents=True, exist_ok=True)
        plot_forecast_guests(forecast_df, figures_dir / "01_forecast_guests.png")
    except Exception as exc:
        warnings.append(f"график не сохранён: {exc}")

    return PipelineResult(forecast=forecast_df, warnings=warnings)
