from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import cast

import lightgbm as lgb
import pandas as pd
import typer
from rich.console import Console
from rich.table import Table

from crocs.ml.baseline import build_future_calendar, calculate_forecast_metrics
from crocs.ml.features import add_calendar_features, add_lag_features, build_supervised_frame
from crocs.ml.lightgbm_model import predict_lightgbm, train_lightgbm

app = typer.Typer(no_args_is_help=False)
console = Console()


@app.command()
def main(
    train_path: Path = Path("data/raw/train.csv"),
    output_dir: Path = Path("data/output"),
    start: str = "2026-04-27",
    end: str = "2026-05-03",
    validation_start: str = "2026-03-01",
    train_start: str | None = None,
) -> None:
    train = pd.read_csv(train_path)
    forecast_start = date.fromisoformat(start)
    forecast_end = date.fromisoformat(end)
    validation_start_date = date.fromisoformat(validation_start)
    train_start_date = date.fromisoformat(train_start) if train_start else None

    console.print("[bold]Validation metrics[/bold]")
    metrics = _validate_lightgbm(train, validation_start_date, train_start_date)
    _print_metrics(metrics)

    train_for_final = _filter_by_train_start(train, train_start_date)
    train_frame = build_supervised_frame(train_for_final)
    model = train_lightgbm(train_frame)
    future_calendar = build_future_calendar(forecast_start, forecast_end)
    forecast = _recursive_forecast(model, train_for_final, future_calendar)

    console.print()
    console.print("[bold]Forecast summary[/bold]")
    _print_forecast_summary(forecast)

    forecast_path, metrics_path = _next_output_paths(output_dir)
    forecast.to_excel(forecast_path, index=False, engine="xlsxwriter")
    pd.DataFrame([metrics]).to_csv(metrics_path, index=False)

    console.print()
    console.print(f"[green]Saved forecast:[/green] {forecast_path}")
    console.print(f"[green]Saved metrics:[/green] {metrics_path}")


def _validate_lightgbm(
    train: pd.DataFrame,
    validation_start: date,
    train_start: date | None,
) -> dict[str, float]:
    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared = _filter_by_train_start(prepared, train_start)

    validation_start_ts = pd.Timestamp(validation_start)
    train_part = cast(pd.DataFrame, prepared[prepared["sale_date"] < validation_start_ts])
    actual_part = cast(pd.DataFrame, prepared[prepared["sale_date"] >= validation_start_ts])

    train_frame = build_supervised_frame(train_part)
    model = train_lightgbm(train_frame)

    validation_calendar = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour"]].copy())
    predicted = _recursive_forecast(model, train_part, validation_calendar)

    actual = cast(pd.DataFrame, actual_part[["sale_date", "sale_hour", "guests_count"]].copy())
    sale_date = cast(pd.Series, actual["sale_date"])
    actual["sale_date"] = sale_date.dt.date
    return calculate_forecast_metrics(actual, predicted)


def _filter_by_train_start(train: pd.DataFrame, train_start: date | None) -> pd.DataFrame:
    if train_start is None:
        return train

    prepared = train.copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    filtered = prepared[prepared["sale_date"] >= pd.Timestamp(train_start)]
    return cast(pd.DataFrame, filtered)


def _recursive_forecast(
    model: lgb.LGBMRegressor,
    history: pd.DataFrame,
    target_calendar: pd.DataFrame,
) -> pd.DataFrame:
    history_frame = _prepare_history(history)
    calendar = _prepare_calendar(target_calendar)
    predictions: list[pd.DataFrame] = []

    for sale_date in sorted(cast(pd.Series, calendar["sale_date"]).unique().tolist()):
        current_calendar = cast(pd.DataFrame, calendar[calendar["sale_date"] == sale_date].copy())
        current_rows = current_calendar.copy()
        current_rows["guests_count"] = pd.NA

        combined = pd.concat([history_frame, current_rows], ignore_index=True)
        featured = add_lag_features(add_calendar_features(combined))
        current_features = cast(pd.DataFrame, featured[featured["sale_date"] == sale_date].copy())

        current_prediction = predict_lightgbm(model, current_features)
        current_output = current_calendar.copy()
        current_output["guests_count"] = (
            current_prediction.round().clip(lower=0).astype(int).to_numpy()
        )
        predictions.append(current_output)

        history_frame = pd.concat([history_frame, current_output], ignore_index=True)

    forecast = pd.concat(predictions, ignore_index=True)
    sale_date_series = cast(pd.Series, forecast["sale_date"])
    forecast["sale_date"] = pd.to_datetime(sale_date_series).dt.date
    return cast(pd.DataFrame, forecast[["sale_date", "sale_hour", "guests_count"]])


def _prepare_history(history: pd.DataFrame) -> pd.DataFrame:
    prepared = history[["sale_date", "sale_hour", "guests_count"]].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    prepared["guests_count"] = prepared["guests_count"].astype(float)
    return cast(pd.DataFrame, prepared)


def _prepare_calendar(target_calendar: pd.DataFrame) -> pd.DataFrame:
    prepared = target_calendar[["sale_date", "sale_hour"]].copy()
    prepared["sale_date"] = pd.to_datetime(prepared["sale_date"], errors="raise")
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    return cast(pd.DataFrame, prepared)


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
        forecast_path = output_dir / f"lightgbm_forecast{index}.xlsx"
        metrics_path = output_dir / f"lightgbm_forecast{index}_metrics.csv"
        if not forecast_path.exists() and not metrics_path.exists():
            return forecast_path, metrics_path
        index += 1


if __name__ == "__main__":
    app()
