from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", type=Path, default=Path("data/raw"))
    p.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    p.add_argument("--check-only", action="store_true")
    args = p.parse_args(argv)

    if args.check_only:
        from crocs.services.pipeline_service import check_raw_present

        try:
            check_raw_present(args.data_dir)
        except Exception as exc:  # noqa: BLE001
            print(exc, file=sys.stderr)
            return 1
        print("OK", args.data_dir)
        return 0

    from crocs.services.pipeline_service import run_pipeline

    try:
        result = run_pipeline(args.data_dir, args.artifacts_dir)
    except NotImplementedError as exc:
        print(exc, file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001
        print(exc, file=sys.stderr)
        return 1

    for w in result.warnings:
        print(w, file=sys.stderr)
    print(args.artifacts_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
