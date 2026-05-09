from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from crocs.config import load_settings

app = typer.Typer(no_args_is_help=True)
console = Console()


@app.command("check-data")
def check_data(config: Path = Path("configs/default.yaml")) -> None:
    settings = load_settings(config)

    from crocs.services.pipeline_service import check_raw_present

    check_raw_present(settings.paths.raw_data_dir)
    console.print(f"OK: raw data found in {settings.paths.raw_data_dir}")


@app.command("run-all")
def run_all(config: Path = Path("configs/default.yaml")) -> None:
    settings = load_settings(config)

    from crocs.services.pipeline_service import run_pipeline

    run_pipeline(
        settings.paths.raw_data_dir,
        settings.paths.output_dir,
        settings=settings,
    )
    console.print(f"Outputs: {settings.paths.output_dir.resolve()}")


def main(argv: list[str] | None = None) -> int:
    try:
        app(args=argv, prog_name="crocs")
    except NotImplementedError as exc:
        console.print(str(exc), style="bold yellow")
        return 2
    except Exception as exc:
        console.print(str(exc), style="bold red")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
