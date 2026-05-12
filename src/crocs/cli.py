from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from crocs.exceptions import DataValidationError, ScheduleError
from crocs.io.csv_repository import _load_table
from crocs.services.pipeline_service import check_raw_present, run_pipeline


def _configure_console_output() -> None:
    """Windows console safety: never fail on unsupported codepage chars."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError, AttributeError, TypeError):
                pass


def _configure_numeric_threads() -> None:
    """Reduce BLAS/OpenMP pressure to avoid OpenBLAS allocation failures."""
    defaults = {
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    for key, value in defaults.items():
        os.environ.setdefault(key, value)


def _convert_xlsx_to_csv(data_dir: Path) -> int:
    stems = ("train", "reqlabor", "weather", "weather_moscow")
    converted = 0
    for stem in stems:
        xlsx_path = data_dir / f"{stem}.xlsx"
        csv_path = data_dir / f"{stem}.csv"
        if not xlsx_path.exists():
            continue
        if csv_path.exists():
            continue
        df = _load_table(data_dir, stem)
        if df is None:
            continue
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(csv_path, index=False)
        converted += 1
    return converted


def main(argv: list[str] | None = None) -> int:
    _configure_console_output()
    _configure_numeric_threads()
    p = argparse.ArgumentParser()
    p.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Каталог для ML: train, weather (по умолчанию data/raw).",
    )
    p.add_argument(
        "--forecast-input-dir",
        "--schedule-input-dir",
        type=Path,
        default=None,
        dest="forecast_input_dir",
        help="Каталог с forecast.xlsx при guests_source=file (по умолчанию paths.forecast_input_dir из YAML). "
        "Алиас: --schedule-input-dir.",
    )
    p.add_argument(
        "--guests-source",
        choices=("model", "file"),
        default=None,
        help="Откуда брать почасовых гостей: model — CatBoost по train; file — готовый forecast.xlsx. "
        "По умолчанию — из YAML (forecast.guests_source).",
    )
    p.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config: окно прогноза и часы ресторана (default: configs/default.yaml).",
    )
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--convert-xlsx-to-csv", action="store_true")
    cli_argv = list(sys.argv[1:] if argv is None else argv)
    if cli_argv and cli_argv[0] == "run":
        cli_argv = cli_argv[1:]
    args = p.parse_args(cli_argv)

    if args.convert_xlsx_to_csv:
        n = _convert_xlsx_to_csv(args.data_dir)
        print(f"Converted {n} file(s) from xlsx to csv in {args.data_dir}")
        return 0

    if args.check_only:
        check_raw_present(
            args.data_dir,
            args.forecast_input_dir,
            config_path=args.config,
            guests_source=args.guests_source,
        )
        print("OK")
        return 0

    print(
        "Пайплайн ML-прогноза гостей: "
        f"raw={args.data_dir.resolve()}, forecast_input={args.forecast_input_dir or '(из YAML)'} "
        f"-> артефакты={args.artifacts_dir.resolve()}",
        flush=True,
    )

    try:
        result = run_pipeline(
            args.data_dir,
            args.artifacts_dir,
            config_path=args.config,
            forecast_input_dir=args.forecast_input_dir,
            guests_source=args.guests_source,
        )
    except (DataValidationError, ScheduleError) as exc:
        print(f"Ошибка входных данных: {exc}", flush=True)
        return 1
    except Exception as exc:
        print(f"Сбой пайплайна: {exc}", flush=True)
        return 1

    for line in result.warnings:
        print(line, flush=True)
    print("Done", flush=True)
    return 0
