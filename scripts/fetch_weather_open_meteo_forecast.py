# ruff: noqa: B008

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import typer
from rich.console import Console

from crocs.config import FORECAST_END
from crocs.io.csv_repository import _load_table
from crocs.ml.features import MODEL_TRAIN_START

app = typer.Typer(no_args_is_help=False)
console = Console()

OPEN_METEO_HISTORICAL_FORECAST_URL = "https://historical-forecast-api.open-meteo.com/v1/forecast"

# Vkusno i tochka near m. Aeroport, TK Galereya Aeroport, Leningradsky pr. 62A.
DEFAULT_LATITUDE = 55.8004
DEFAULT_LONGITUDE = 37.5325
DEFAULT_TIMEZONE = "Europe/Moscow"
DEFAULT_HOURLY = ("temperature_2m", "precipitation")


@app.command()
def main(
    data_dir: Path = typer.Option(
        Path("data/raw"),
        "--data-dir",
        "-d",
        help="Directory with train.csv and output weather CSV.",
    ),
    output_name: str = typer.Option(
        "weather_moscow_open_meteo_forecast.csv",
        "--output-name",
        help="Weather CSV name inside data-dir.",
    ),
    latitude: float = typer.Option(
        DEFAULT_LATITUDE,
        "--latitude",
        help="PBO latitude. Default is m. Aeroport / Galereya Aeroport area.",
    ),
    longitude: float = typer.Option(
        DEFAULT_LONGITUDE,
        "--longitude",
        help="PBO longitude. Default is m. Aeroport / Galereya Aeroport area.",
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
    timeout_seconds: int = typer.Option(
        60,
        "--timeout-seconds",
        help="HTTP timeout.",
    ),
) -> None:
    train = _load_table(data_dir, "train")
    if train is None:
        raise FileNotFoundError(f"No train.csv/train.xlsx found in {data_dir.resolve()}")

    train_dates = pd.to_datetime(train["sale_date"], errors="raise")
    first_date = (
        date.fromisoformat(start)
        if start
        else max(
            train_dates.min().date(),
            MODEL_TRAIN_START.date(),
        )
    )
    last_date = (
        date.fromisoformat(end)
        if end
        else max(
            train_dates.max().date(),
            FORECAST_END,
        )
    )
    if first_date > last_date:
        raise ValueError("--start must be earlier than or equal to --end")

    console.print(
        "[cyan]Fetching Open-Meteo historical forecast[/cyan] "
        f"{first_date}..{last_date} at {latitude:.4f},{longitude:.4f}"
    )
    payload = fetch_open_meteo_historical_forecast(
        latitude=latitude,
        longitude=longitude,
        start_date=first_date,
        end_date=last_date,
        timeout_seconds=timeout_seconds,
    )
    weather = parse_open_meteo_hourly(payload)

    output_path = data_dir / output_name
    output_path.parent.mkdir(parents=True, exist_ok=True)
    weather.to_csv(output_path, index=False)
    console.print(f"[green]Saved weather forecast:[/green] {output_path} ({len(weather)} rows)")


def fetch_open_meteo_historical_forecast(
    *,
    latitude: float,
    longitude: float,
    start_date: date,
    end_date: date,
    timeout_seconds: int,
) -> dict[str, Any]:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "hourly": ",".join(DEFAULT_HOURLY),
        "timezone": DEFAULT_TIMEZONE,
        "temperature_unit": "celsius",
        "precipitation_unit": "mm",
    }
    url = f"{OPEN_METEO_HISTORICAL_FORECAST_URL}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "crocs-kaggle-weather/1.0"})
    with urlopen(request, timeout=timeout_seconds) as response:
        text = response.read().decode("utf-8")
    return json.loads(text)


def parse_open_meteo_hourly(payload: dict[str, Any]) -> pd.DataFrame:
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        reason = payload.get("reason", "missing hourly data")
        raise ValueError(f"Open-Meteo response has no hourly data: {reason}")

    frame = pd.DataFrame(
        {
            "forecast_at_local": pd.to_datetime(hourly["time"], errors="raise"),
            "temp_c": hourly.get("temperature_2m"),
            "precipitation_mm": hourly.get("precipitation"),
        }
    )
    frame["sale_date"] = frame["forecast_at_local"].dt.date
    frame["sale_hour"] = frame["forecast_at_local"].dt.hour.astype(int)
    frame["source"] = "open-meteo-historical-forecast"
    frame["model"] = "best_match"

    return (
        frame[
            [
                "source",
                "model",
                "forecast_at_local",
                "sale_date",
                "sale_hour",
                "temp_c",
                "precipitation_mm",
            ]
        ]
        .sort_values(["forecast_at_local"])
        .reset_index(drop=True)
    )


if __name__ == "__main__":
    app()
