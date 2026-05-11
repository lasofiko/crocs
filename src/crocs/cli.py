from __future__ import annotations

import argparse
import os
from pathlib import Path

from crocs.exceptions import DataValidationError, ScheduleError
from crocs.io.csv_repository import _load_table
from crocs.services.pipeline_service import check_raw_present, run_pipeline


def _configure_console_output() -> None:
    """Windows console safety: never fail on unsupported codepage chars."""
    import sys

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
    stems = (
        "train",
        "reqlabor",
        "sched",
        "station_priorities",
        "shifts",
        "staff_limits",
    )
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
        help="Каталог для ML и спроса: train, reqlabor, weather (по умолчанию data/raw).",
    )
    p.add_argument(
        "--schedule-input-dir",
        type=Path,
        default=None,
        help="Каталог для оптимизации: sched, station_priorities, shifts, staff_limits; "
        "при forecast.guests_source=file — ещё и forecast.xlsx (по умолчанию paths.schedule_input_dir, часто data/output).",
    )
    p.add_argument(
        "--guests-source",
        choices=("model", "file"),
        default=None,
        help="Откуда брать почасовых гостей: model — CatBoost по train; file — готовый outputs.forecast из schedule_input_dir. "
        "По умолчанию — из YAML (forecast.guests_source).",
    )
    p.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    p.add_argument(
        "--config",
        type=Path,
        default=None,
        help="YAML config: forecast window and restaurant hours (default: configs/default.yaml).",
    )
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--convert-xlsx-to-csv", action="store_true")
    args = p.parse_args(argv)

    if args.convert_xlsx_to_csv:
        n = _convert_xlsx_to_csv(args.data_dir)
        print(f"Converted {n} file(s) from xlsx to csv in {args.data_dir}")
        return 0

    if args.check_only:
        check_raw_present(
            args.data_dir,
            args.schedule_input_dir,
            config_path=args.config,
            guests_source=args.guests_source,
        )
        print("OK")
        return 0

    print(
        "Пайплайн (спрос + расписание): "
        f"raw={args.data_dir.resolve()}, schedule_input={args.schedule_input_dir or '(из YAML)'} "
        f"-> артефакты={args.artifacts_dir.resolve()}",
        flush=True,
    )

    try:
        result = run_pipeline(
            args.data_dir,
            args.artifacts_dir,
            config_path=args.config,
            schedule_input_dir=args.schedule_input_dir,
            guests_source=args.guests_source,
        )
    except DataValidationError as exc:
        print(f"Ошибка входных данных: {exc}", flush=True)
        return 1
    except ScheduleError as exc:
        msg = str(exc)
        infl = (
            "INFEASIBLE" in msg
            or "недостижим" in msg.lower()
            or "UNKNOWN" in msg
        )
        result = None

        cp_sat_cfg = Path("configs/cp_sat.yaml")
        cp_sat_relaxed_cfg = Path("configs/cp_sat_relaxed.yaml")
        if (
            infl
            and args.config is not None
            and cp_sat_relaxed_cfg.is_file()
            and args.config.resolve() == cp_sat_cfg.resolve()
        ):
            print(
                "Расписание недостижимо на configs/cp_sat.yaml; "
                "повтор с configs/cp_sat_relaxed.yaml…",
                flush=True,
            )
            try:
                result = run_pipeline(
                    args.data_dir,
                    args.artifacts_dir,
                    config_path=cp_sat_relaxed_cfg,
                    schedule_input_dir=args.schedule_input_dir,
                    guests_source=args.guests_source,
                )
            except ScheduleError as exc_relaxed:
                print(f"Ошибка расписания (cp_sat_relaxed): {exc_relaxed}", flush=True)
                return 1

        relaxed_cfg = Path("configs/relaxed_scheduling.yaml")
        can_retry_relaxed = (
            result is None
            and infl
            and args.config is None
            and relaxed_cfg.is_file()
        )
        if can_retry_relaxed:
            print(
                "Расписание недостижимо или не успело на default-конфиге; "
                "повтор с configs/relaxed_scheduling.yaml…",
                flush=True,
            )
            try:
                result = run_pipeline(
                    args.data_dir,
                    args.artifacts_dir,
                    config_path=relaxed_cfg,
                    schedule_input_dir=args.schedule_input_dir,
                    guests_source=args.guests_source,
                )
            except Exception as relaxed_exc:
                print(f"Ошибка после relaxed-конфига: {relaxed_exc}", flush=True)
                return 1
        elif result is None:
            print(f"Ошибка расписания: {exc}", flush=True)
            return 1
    except Exception as exc:
        print(f"Сбой пайплайна: {exc}", flush=True)
        return 1

    for line in result.warnings:
        print(line, flush=True)
    print("Done", flush=True)
    return 0
