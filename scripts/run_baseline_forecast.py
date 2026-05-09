from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from crocs.ml.baseline import (
    build_future_calendar,
    calculate_forecast_metrics,
    predict_median_by_weekday_hour,
)

app = typer.Typer(no_args_is_help=False)
console = Console()


@app.command()
def main(
    train_path: Path = Path("data/raw/train.csv"),
    output_dir: Path = Path("data/output"),
    start: str = "2026-04-27",
    end: str = "2026-05-03",
    window_weeks: int = 12,
    validation_start: str = "2026-03-01",
) -> None:
    train = pd.read_csv(train_path)
    forecast_start = date.fromisoformat(start)
    forecast_end = date.fromisoformat(end)
    validation_start_date = date.fromisoformat(validation_start)

    future_calendar = build_future_calendar(forecast_start, forecast_end)
    forecast = predict_median_by_weekday_hour(
        train,
        future_calendar,
        window_weeks=window_weeks,
    )

    console.print("[bold]Forecast summary[/bold]")
    _print_forecast_summary(forecast)

    console.print()
    console.print("[bold]Validation metrics[/bold]")
    metrics = _validate_baseline(train, validation_start_date, window_weeks)
    _print_metrics(metrics)

    forecast_path, metrics_path = _next_output_paths(output_dir)
    forecast.to_excel(forecast_path, index=False, engine="xlsxwriter")
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)

    console.print()
    console.print(f"[green]Saved forecast:[/green] {forecast_path}")
    console.print(f"[green]Saved metrics:[/green] {metrics_path}")


def _validate_baseline(
    train: pd.DataFrame,
    validation_start: date,
    window_weeks: int,
) -> dict[str, float]:
    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")

    validation_start_ts = pd.Timestamp(validation_start)
    train_part = cast(pd.DataFrame, prepared[prepared["sale_date"] < validation_start_ts])
    actual_part = cast(pd.DataFrame, prepared[prepared["sale_date"] >= validation_start_ts])
    validation_calendar = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour"]].copy())

    predicted = predict_median_by_weekday_hour(
        train_part,
        validation_calendar,
        window_weeks=window_weeks,
    )
    actual = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour", "guests_count"]].copy())
    sale_date = cast(pd.Series, actual["sale_date"])
    actual["sale_date"] = sale_date.dt.date
    return calculate_forecast_metrics(actual, predicted)


def _print_forecast_summary(forecast: pd.DataFrame) -> None:
    table = Table()
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    table.add_row("Rows", str(len(forecast)))
    table.add_row("Date min", str(forecast["sale_date"].min()))
    table.add_row("Date max", str(forecast["sale_date"].max()))
    table.add_row("Hour min", str(forecast["sale_hour"].min()))
    table.add_row("Hour max", str(forecast["sale_hour"].max()))
    table.add_row("Guests min", str(forecast["guests_count"].min()))
    table.add_row("Guests max", str(forecast["guests_count"].max()))
    table.add_row("Guests total", str(forecast["guests_count"].sum()))
    console.print(table)

    console.print()
    console.print(forecast.head(16).to_string(index=False))


def _print_metrics(metrics: dict[str, float]) -> None:
    table = Table()
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in metrics.items():
        table.add_row(key, f"{value:.4f}")
    console.print(table)


def _next_output_paths(output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        forecast_path = output_dir / f"forecast{index}.xlsx"
        metrics_path = output_dir / f"forecast{index}_metrics.csv"
        if not forecast_path.exists() and not metrics_path.exists():
            return forecast_path, metrics_path
        index += 1


if __name__ == "__main__":
    app()
