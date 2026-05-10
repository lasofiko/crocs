# ruff: noqa: B008

from __future__ import annotations

import calendar
import time
from datetime import date
from pathlib import Path
from typing import cast

import pandas as pd
import typer
from rich.console import Console

from crocs.config import FORECAST_END
from crocs.io.csv_repository import _load_table
from crocs.ml.features import MODEL_TRAIN_START
from crocs.ml.weather import MOSCOW_WEATHER_STATION_ID, WeatherRequest, fetch_weather_month

app = typer.Typer(no_args_is_help=False)
console = Console()


@app.command()
def main(
    data_dir: Path = typer.Option(
        Path("data/raw"),
        "--data-dir",
        "-d",
        help="Directory with train.csv and output weather_moscow.csv.",
    ),
    output_name: str = typer.Option(
        "weather_moscow.csv",
        "--output-name",
        help="Weather CSV name inside data-dir.",
    ),
    station_id: int = typer.Option(
        MOSCOW_WEATHER_STATION_ID,
        "--station-id",
        help="pogodaiklimat.ru station id. 27612 is Moscow station near metro Aeroport.",
    ),
    start: str | None = typer.Option(
        None,
        "--start",
        help="First date to fetch. Default: max(train min date, 2022-09-22).",
    ),
    end: str | None = typer.Option(
        None,
        "--end",
        help="Last date to fetch. Default: max(train max date, forecast end).",
    ),
    sleep_seconds: float = typer.Option(
        0.4,
        "--sleep-seconds",
        help="Pause between month requests.",
    ),
) -> None:
    train = _load_table(data_dir, "train")
    if train is None:
        raise FileNotFoundError(f"No train.csv/train.xlsx found in {data_dir.resolve()}")

    train_dates = pd.to_datetime(train["sale_date"], errors="raise")
    first_date = date.fromisoformat(start) if start else max(
        cast(date, train_dates.min().date()),
        MODEL_TRAIN_START.date(),
    )
    last_date = date.fromisoformat(end) if end else max(
        cast(date, train_dates.max().date()),
        FORECAST_END,
    )
    if first_date > last_date:
        raise ValueError("--start must be earlier than or equal to --end")

    frames: list[pd.DataFrame] = []
    for year, month, first_day, last_day in _month_ranges(first_date, last_date):
        request = WeatherRequest(
            station_id=station_id,
            first_day=first_day,
            last_day=last_day,
            month=month,
            year=year,
        )
        console.print(
            f"[cyan]Fetching weather[/cyan] {year}-{month:02d}: "
            f"{first_day:02d}..{last_day:02d}"
        )
        frames.append(fetch_weather_month(request))
        time.sleep(sleep_seconds)

    weather = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    weather = weather.drop_duplicates(["observed_at_local"]).sort_values("observed_at_local")

    output_path = data_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weather.to_csv(output_path, index=False)
    console.print(f"[green]Saved weather:[/green] {output_path} ({len(weather)} rows)")


def _month_ranges(first_date: date, last_date: date) -> list[tuple[int, int, int, int]]:
    current = date(first_date.year, first_date.month, 1)
    result: list[tuple[int, int, int, int]] = []

    while current <= last_date:
        days_in_month = calendar.monthrange(current.year, current.month)[1]
        month_start = date(current.year, current.month, 1)
        month_end = date(current.year, current.month, days_in_month)
        is_first_month = current.year == first_date.year and current.month == first_date.month
        is_last_month = current.year == last_date.year and current.month == last_date.month
        first_day = first_date.day if is_first_month else 1
        last_day = last_date.day if is_last_month else month_end.day
        if month_end >= first_date and month_start <= last_date:
            result.append((current.year, current.month, first_day, last_day))
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)

    return result


if __name__ == "__main__":
    app()
