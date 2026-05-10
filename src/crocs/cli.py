from __future__ import annotations

import argparse
import os
from pathlib import Path

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
    from crocs.io.csv_repository import _load_table

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
        # Do not overwrite an existing CSV without an explicit request.
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
    p.add_argument("--data-dir", type=Path, default=Path("data/raw"))
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
        from crocs.services.pipeline_service import check_raw_present

        check_raw_present(args.data_dir)
        print("OK")
        return 0

    print(
        "Пайплайн (прогноз + расписание): "
        f"данные={args.data_dir.resolve()} -> артефакты={args.artifacts_dir.resolve()}",
        flush=True,
    )
    from crocs.exceptions import DataValidationError, ScheduleError
    from crocs.services.pipeline_service import run_pipeline

    try:
        result = run_pipeline(args.data_dir, args.artifacts_dir, config_path=args.config)
    except DataValidationError as exc:
        print(f"Ошибка входных данных: {exc}", flush=True)
        return 1
    except ScheduleError as exc:
        msg = str(exc)
        relaxed_cfg = Path("configs/relaxed_scheduling.yaml")
        can_retry_relaxed = args.config is None and relaxed_cfg.exists() and "INFEASIBLE" in msg
        if can_retry_relaxed:
            print(
                "CP-SAT вернул INFEASIBLE на default-конфиге; пробую автоматически relaxed-конфиг...",
                flush=True,
            )
            try:
                result = run_pipeline(args.data_dir, args.artifacts_dir, config_path=relaxed_cfg)
            except Exception as relaxed_exc:
                print(f"Ошибка расписания (после relaxed): {relaxed_exc}", flush=True)
                return 1
        else:
            print(f"Ошибка расписания: {exc}", flush=True)
            return 1
    except Exception as exc:
        print(f"Сбой пайплайна: {exc}", flush=True)
        return 1
    for line in result.warnings:
        print(line, flush=True)
    print("Done", flush=True)
    return 0