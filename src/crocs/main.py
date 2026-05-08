from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Пайплайн прогноза гостей и расписания персонала",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/raw"),
        help="Каталог с train.csv, reqlabor.csv, …",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output"),
        help="Куда сохранить forecast.xlsx и schedule.xlsx",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Только проверить, что все входные CSV присутствуют",
    )
    args = parser.parse_args(argv)

    if args.check_only:
        from crocs.pipeline import check_raw_present

        try:
            check_raw_present(args.data_dir)
        except Exception as exc:  # noqa: BLE001
            print(exc, file=sys.stderr)
            return 1
        print("OK: все файлы из ТЗ найдены в", args.data_dir)
        return 0

    from crocs.pipeline import run_pipeline

    try:
        result = run_pipeline(args.data_dir, args.output_dir)
    except NotImplementedError as exc:
        print("Следующий шаг — реализация:", exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        return 1

    if result.warnings:
        for w in result.warnings:
            print("Предупреждение:", w, file=sys.stderr)
    print("Сохранено в", args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
