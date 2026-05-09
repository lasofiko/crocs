from __future__ import annotations

import argparse
from pathlib import Path

from crocs.services.pipeline_service import run_pipeline, check_raw_present
from crocs.io.csv_repository import _load_table


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
        # Не перезаписываем существующий csv без запроса.
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
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    p.add_argument("--check-only", action="store_true")
    p.add_argument("--convert-xlsx-to-csv", action="store_true")
    args = p.parse_args(argv)

    if args.convert_xlsx_to_csv:
        n = _convert_xlsx_to_csv(args.data_dir)
        print(f"Converted {n} file(s) from xlsx to csv in {args.data_dir}")
        return 0

    if args.check_only:
        check_raw_present(args.data_dir)
        print("OK")
        return 0

    run_pipeline(args.data_dir, args.artifacts_dir)
    print("Done")
    return 0