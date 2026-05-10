# ruff: noqa: B008

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from crocs.config import RESTAURANT_CLOSE_HOUR, RESTAURANT_OPEN_HOUR
from crocs.io.csv_repository import _load_table
from crocs.ml.baseline import calculate_forecast_metrics
from crocs.ml.features import MODEL_TRAIN_START, build_supervised_frame
from crocs.ml.lightgbm_model import train_lightgbm
from crocs.ml.lightgbm_pipeline import recursive_forecast, run_lightgbm_forecast

app = typer.Typer(no_args_is_help=False)
console = Console()


@app.command()
def main(
    data_dir: Path = typer.Option(
        Path("data/output"),
        "--data-dir",
        "-d",
        help="Directory with train.csv or train.xlsx.",
    ),
    output_dir: Path = typer.Option(
        Path("data/output"),
        "--output-dir",
        "-o",
        help="Directory for forecast, hold-out metrics, and CV metrics.",
    ),
    start: str = "2026-04-27",
    end: str = "2026-05-03",
    validation_start: str = "2026-03-01",
    train_start: str | None = None,
    cv_folds: int = 4,
    open_hour: int = RESTAURANT_OPEN_HOUR,
    close_hour: int = RESTAURANT_CLOSE_HOUR,
) -> None:
    train = _load_table(data_dir, "train")
    if train is None:
        raise FileNotFoundError(
            f"No train file found: put train.csv or train.xlsx into {data_dir.resolve()}"
        )
    forecast_start = date.fromisoformat(start)
    forecast_end = date.fromisoformat(end)
    validation_start_date = date.fromisoformat(validation_start)
    train_start_date = date.fromisoformat(train_start) if train_start else None

    hours = tuple(range(open_hour, close_hour))

    console.print("[bold]Validation metrics[/bold]")
    metrics = _validate_lightgbm(
        train,
        validation_start_date,
        train_start_date,
        hours=hours,
    )
    _print_metrics(metrics)

    console.print()
    console.print("[bold]Rolling CV metrics[/bold]")
    cv_metrics = _cross_validate_lightgbm(
        train,
        train_start_date,
        hours=hours,
        folds=cv_folds,
    )
    if cv_metrics.empty:
        console.print("[yellow]Not enough history for rolling CV.[/yellow]")
    else:
        console.print(cv_metrics.to_string(index=False))
        console.print()
        console.print("[bold]Rolling CV mean[/bold]")
        _print_metrics(
            {
                "mae": float(cv_metrics["mae"].mean()),
                "rmse": float(cv_metrics["rmse"].mean()),
                "wape": float(cv_metrics["wape"].mean()),
                "rows": float(cv_metrics["rows"].sum()),
            }
        )

    train_for_final = _filter_by_train_start(train, train_start_date)
    forecast = run_lightgbm_forecast(
        train_for_final,
        forecast_start=forecast_start,
        forecast_end=forecast_end,
        open_hour=open_hour,
        close_hour=close_hour,
    )

    console.print()
    console.print("[bold]Forecast summary[/bold]")
    _print_forecast_summary(forecast)

    forecast_path, metrics_path, cv_metrics_path = _next_output_paths(output_dir)
    forecast.to_excel(forecast_path, index=False, engine="openpyxl")
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)
    cv_metrics.to_csv(cv_metrics_path, index=False)

    console.print()
    console.print(f"[green]Saved forecast:[/green] {forecast_path}")
    console.print(f"[green]Saved metrics:[/green] {metrics_path}")
    console.print(f"[green]Saved CV metrics:[/green] {cv_metrics_path}")


def _resolve_train_validation_split(
    prepared: pd.DataFrame,
    validation_start: date,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    """Train = dates strictly before split; validation = from split onward.

    If ``validation_start`` leaves no training rows (all data after that date),
    split on the **last** calendar day in the data so earlier days are train.
    """
    validation_start_ts = pd.Timestamp(validation_start)
    norm = prepared["sale_date"].dt.normalize()
    train_part = cast(pd.DataFrame, prepared[norm < validation_start_ts.normalize()])
    actual_part = cast(pd.DataFrame, prepared[norm >= validation_start_ts.normalize()])

    if not train_part.empty and not actual_part.empty:
        return train_part, actual_part, validation_start_ts

    days = sorted(norm.unique())
    if len(days) < 2:
        raise ValueError(
            "Train needs at least two different calendar days to calculate hold-out "
            "metrics. Extend history or set --validation-start before the first date."
        )

    split_ts = cast(pd.Timestamp, days[-1])
    train_part = cast(pd.DataFrame, prepared[norm < split_ts])
    actual_part = cast(pd.DataFrame, prepared[norm >= split_ts])
    console.print(
        "[yellow]All train dates are after --validation-start; "
        f"hold-out moved to the last data day ({split_ts.date()}).[/yellow]"
    )
    return train_part, actual_part, split_ts


def _validate_lightgbm(
    train: pd.DataFrame,
    validation_start: date,
    train_start: date | None,
    *,
    hours: tuple[int, ...],
) -> dict[str, float]:
    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared = _filter_by_train_start(prepared, train_start)

    train_part, actual_part, _ = _resolve_train_validation_split(prepared, validation_start)

    train_frame = build_supervised_frame(train_part, hours=hours)
    model = train_lightgbm(train_frame)

    validation_calendar = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour"]].copy())
    predicted = recursive_forecast(model, train_part, validation_calendar)

    actual = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour", "guests_count"]].copy())
    sale_date = cast(pd.Series, actual["sale_date"])
    actual["sale_date"] = sale_date.dt.date
    return calculate_forecast_metrics(actual, predicted)


def _cross_validate_lightgbm(
    train: pd.DataFrame,
    train_start: date | None,
    *,
    hours: tuple[int, ...],
    folds: int,
) -> pd.DataFrame:
    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared = _filter_by_train_start(prepared, train_start)
    prepared = prepared[prepared["sale_date"] >= MODEL_TRAIN_START]
    if prepared.empty or folds <= 0:
        return pd.DataFrame()

    days = sorted(prepared["sale_date"].dt.normalize().unique())
    rows: list[dict[str, float | int | str]] = []

    for fold_index in range(folds, 0, -1):
        val_end = cast(pd.Timestamp, days[-1]) - pd.Timedelta(days=7 * (fold_index - 1))
        val_start = val_end - pd.Timedelta(days=6)
        train_part = cast(pd.DataFrame, prepared[prepared["sale_date"] < val_start])
        actual_part = cast(
            pd.DataFrame,
            prepared[prepared["sale_date"].between(val_start, val_end)],
        )
        if train_part.empty or actual_part.empty:
            continue

        train_frame = build_supervised_frame(train_part, hours=hours)
        if train_frame.empty:
            continue
        model = train_lightgbm(train_frame)
        validation_calendar = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour"]].copy())
        predicted = recursive_forecast(model, train_part, validation_calendar)

        actual = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour", "guests_count"]].copy())
        sale_date = cast(pd.Series, actual["sale_date"])
        actual["sale_date"] = sale_date.dt.date
        metrics = calculate_forecast_metrics(actual, predicted)
        rows.append(
            {
                "fold": folds - fold_index + 1,
                "validation_start": str(val_start.date()),
                "validation_end": str(val_end.date()),
                **metrics,
            }
        )

    return pd.DataFrame(rows)


def _filter_by_train_start(train: pd.DataFrame, train_start: date | None) -> pd.DataFrame:
    if train_start is None:
        return train

    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    filtered = prepared[prepared["sale_date"] >= pd.Timestamp(train_start)]
    return cast(pd.DataFrame, filtered)


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


def _next_output_paths(output_dir: Path) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        forecast_path = output_dir / f"lightgbm_forecast{index}.xlsx"
        metrics_path = output_dir / f"lightgbm_forecast{index}_metrics.csv"
        cv_metrics_path = output_dir / f"lightgbm_forecast{index}_cv_metrics.csv"
        if (
            not forecast_path.exists()
            and not metrics_path.exists()
            and not cv_metrics_path.exists()
        ):
            return forecast_path, metrics_path, cv_metrics_path
        index += 1


if __name__ == "__main__":
    app()
