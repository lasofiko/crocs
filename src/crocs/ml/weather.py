from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

MOSCOW_WEATHER_STATION_ID = 27612
MOSCOW_UTC_OFFSET_HOURS = 3
WEATHER_FEATURE_COLUMNS = (
    "has_weather_observation",
    "weather_temp_c",
    "weather_dew_point_c",
    "weather_humidity_pct",
    "weather_effective_temp_c",
    "weather_effective_sun_temp_c",
    "weather_pressure_hpa",
    "weather_station_pressure_hpa",
    "weather_precip_mm",
    "weather_precip_24h_mm",
    "weather_snow_depth_cm",
    "weather_wind_speed_mps",
    "weather_visibility_km",
    "weather_cloud_total_octas",
    "is_weather_precipitation",
    "is_weather_rain",
    "is_weather_snow",
    "is_weather_fog",
    "is_weather_thunderstorm",
)


@dataclass(frozen=True)
class WeatherRequest:
    station_id: int
    first_day: int
    last_day: int
    month: int
    year: int

    def url(self) -> str:
        params = urlencode(
            {
                "id": self.station_id,
                "bday": self.first_day,
                "fday": self.last_day,
                "amonth": self.month,
                "ayear": self.year,
                "bot": 2,
            }
        )
        return f"https://www.pogodaiklimat.ru/weather.php?{params}"


def fetch_weather_month(
    request: WeatherRequest,
    *,
    timeout_seconds: int = 30,
) -> pd.DataFrame:
    """Download and parse one monthly weather archive page."""
    http_request = Request(request.url(), headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(http_request, timeout=timeout_seconds) as response:
        html = response.read().decode("utf-8", errors="replace")
    return parse_pogodaiklimat_archive(
        html,
        year=request.year,
        station_id=request.station_id,
    )


def parse_pogodaiklimat_archive(
    html: str,
    *,
    year: int,
    station_id: int = MOSCOW_WEATHER_STATION_ID,
    utc_offset_hours: int = MOSCOW_UTC_OFFSET_HOURS,
) -> pd.DataFrame:
    """Parse pogodaiklimat.ru archive HTML into exact 3-hour observations."""
    parser = _TableParser()
    parser.feed(html)
    if len(parser.tables) < 2:
        return _empty_weather_frame()

    time_rows = parser.tables[0][1:]
    weather_rows = parser.tables[1][1:]
    rows: list[dict[str, object]] = []

    for time_row, weather_row in zip(time_rows, weather_rows, strict=False):
        if len(time_row) < 2 or len(weather_row) < 18:
            continue

        observed_at_utc = _parse_observed_at_utc(time_row, year=year)
        if observed_at_utc is None:
            continue
        observed_at_local = observed_at_utc + pd.Timedelta(hours=utc_offset_hours)
        event = weather_row[3]

        rows.append(
            {
                "station_id": station_id,
                "observed_at_utc": observed_at_utc,
                "observed_at_local": observed_at_local,
                "sale_date": observed_at_local.date(),
                "sale_hour": int(observed_at_local.hour),
                "wind_direction": weather_row[0],
                "wind_speed_mps": _parse_float(weather_row[1]),
                "visibility_text": weather_row[2],
                "visibility_km": _parse_visibility_km(weather_row[2]),
                "weather_event": event,
                "cloudiness": weather_row[4],
                "cloud_total_octas": _parse_cloud_total_octas(weather_row[4]),
                "temp_c": _parse_float(weather_row[5]),
                "dew_point_c": _parse_float(weather_row[6]),
                "humidity_pct": _parse_float(weather_row[7]),
                "effective_temp_c": _parse_float(weather_row[8]),
                "effective_sun_temp_c": _parse_float(weather_row[9]),
                "comfort": weather_row[10],
                "pressure_hpa": _parse_float(weather_row[11]),
                "station_pressure_hpa": _parse_float(weather_row[12]),
                "temp_min_c": _parse_float(weather_row[13]),
                "temp_max_c": _parse_float(weather_row[14]),
                "precipitation_mm": _parse_float(weather_row[15]),
                "precipitation_24h_mm": _parse_float(weather_row[16]),
                "snow_depth_cm": _parse_float(weather_row[17]),
                **_event_flags(event),
            }
        )

    if not rows:
        return _empty_weather_frame()
    weather = pd.DataFrame(rows)
    return weather.sort_values(["observed_at_local"]).reset_index(drop=True)


def add_weather_features(df: pd.DataFrame, weather: pd.DataFrame | None) -> pd.DataFrame:
    """Join exact-date/hour weather observations without hourly interpolation."""
    featured = df.copy()
    featured_sale_date = pd.to_datetime(featured["sale_date"], errors="raise")
    featured["sale_date"] = featured_sale_date
    featured["_weather_join_date"] = featured_sale_date.dt.date
    featured["sale_hour"] = featured["sale_hour"].astype(int)

    if weather is None or weather.empty:
        featured = _add_empty_weather_features(featured)
        return featured.drop(columns=["_weather_join_date"])

    prepared = _prepare_weather_features(weather)
    featured = featured.merge(
        prepared,
        left_on=["_weather_join_date", "sale_hour"],
        right_on=["weather_join_date", "sale_hour"],
        how="left",
    )
    featured = featured.drop(columns=["_weather_join_date", "weather_join_date"])
    featured["has_weather_observation"] = featured["has_weather_observation"].fillna(0).astype(int)
    for column in WEATHER_FEATURE_COLUMNS:
        if column not in featured.columns:
            featured[column] = pd.NA
    flag_columns = [
        column for column in WEATHER_FEATURE_COLUMNS if column.startswith("is_weather_")
    ]
    for column in flag_columns:
        featured[column] = featured[column].fillna(0).astype(int)
    return featured


def _prepare_weather_features(weather: pd.DataFrame) -> pd.DataFrame:
    prepared = weather.copy()
    prepared["weather_join_date"] = pd.to_datetime(prepared["sale_date"], errors="raise").dt.date
    prepared["sale_hour"] = prepared["sale_hour"].astype(int)
    rename_map = {
        "temp_c": "weather_temp_c",
        "dew_point_c": "weather_dew_point_c",
        "humidity_pct": "weather_humidity_pct",
        "effective_temp_c": "weather_effective_temp_c",
        "effective_sun_temp_c": "weather_effective_sun_temp_c",
        "pressure_hpa": "weather_pressure_hpa",
        "station_pressure_hpa": "weather_station_pressure_hpa",
        "precipitation_mm": "weather_precip_mm",
        "precipitation_24h_mm": "weather_precip_24h_mm",
        "snow_depth_cm": "weather_snow_depth_cm",
        "wind_speed_mps": "weather_wind_speed_mps",
        "visibility_km": "weather_visibility_km",
        "cloud_total_octas": "weather_cloud_total_octas",
    }
    prepared = prepared.rename(columns=rename_map)
    prepared["has_weather_observation"] = 1
    keep = ["weather_join_date", "sale_hour", *WEATHER_FEATURE_COLUMNS]
    keep = [column for column in keep if column in prepared.columns]
    return (
        prepared[keep]
        .sort_values(["weather_join_date", "sale_hour"])
        .drop_duplicates(["weather_join_date", "sale_hour"], keep="last")
    )


def _add_empty_weather_features(df: pd.DataFrame) -> pd.DataFrame:
    featured = df.copy()
    for column in WEATHER_FEATURE_COLUMNS:
        featured[column] = 0 if column.startswith(("has_weather_", "is_weather_")) else pd.NA
    return featured


def _empty_weather_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "station_id",
            "observed_at_utc",
            "observed_at_local",
            "sale_date",
            "sale_hour",
            "wind_direction",
            "wind_speed_mps",
            "visibility_text",
            "visibility_km",
            "weather_event",
            "cloudiness",
            "cloud_total_octas",
            "temp_c",
            "dew_point_c",
            "humidity_pct",
            "effective_temp_c",
            "effective_sun_temp_c",
            "comfort",
            "pressure_hpa",
            "station_pressure_hpa",
            "temp_min_c",
            "temp_max_c",
            "precipitation_mm",
            "precipitation_24h_mm",
            "snow_depth_cm",
            "is_weather_precipitation",
            "is_weather_rain",
            "is_weather_snow",
            "is_weather_fog",
            "is_weather_thunderstorm",
        ]
    )


def _parse_observed_at_utc(time_row: list[str], *, year: int) -> pd.Timestamp | None:
    try:
        hour = int(time_row[0])
        day_text, month_text = time_row[1].split(".", maxsplit=1)
        return pd.Timestamp(year=year, month=int(month_text), day=int(day_text), hour=hour)
    except (IndexError, TypeError, ValueError):
        return None


def _parse_float(value: object) -> float | None:
    text = str(value).strip().replace("+", "").replace(",", ".")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _parse_visibility_km(value: object) -> float | None:
    text = str(value).strip().replace(",", ".")
    if not text:
        return None
    number = _parse_float(text.split()[0])
    if number is None:
        return None
    if "км" in text:
        return number
    if "м" in text:
        return number / 1000
    return number


def _parse_cloud_total_octas(value: object) -> float | None:
    text = str(value).strip()
    if not text:
        return None
    first = text.split()[0]
    if "/" in first:
        first = first.split("/", maxsplit=1)[0]
    return _parse_float(first)


def _event_flags(event: object) -> dict[str, int]:
    text = str(event).lower()
    is_rain = int("дожд" in text or "ливн" in text or "морос" in text)
    is_snow = int("снег" in text or "метел" in text)
    is_fog = int("туман" in text or "дымк" in text or "мгла" in text)
    is_thunderstorm = int("гроз" in text)
    return {
        "is_weather_precipitation": int(is_rain or is_snow or is_thunderstorm),
        "is_weather_rain": is_rain,
        "is_weather_snow": is_snow,
        "is_weather_fog": is_fog,
        "is_weather_thunderstorm": is_thunderstorm,
    }


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self._in_table = False
        self._in_row = False
        self._in_cell = False
        self._table: list[list[str]] = []
        self._row: list[str] = []
        self._cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._in_table = True
            self._table = []
        elif tag == "tr" and self._in_table:
            self._in_row = True
            self._row = []
        elif tag in {"td", "th"} and self._in_row:
            self._in_cell = True
            self._cell = []
        elif tag == "br" and self._in_cell:
            self._cell.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"td", "th"} and self._in_cell:
            self._row.append(" ".join("".join(self._cell).split()))
            self._in_cell = False
        elif tag == "tr" and self._in_row:
            if self._row:
                self._table.append(self._row)
            self._in_row = False
        elif tag == "table" and self._in_table:
            self.tables.append(self._table)
            self._in_table = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell.append(data)
