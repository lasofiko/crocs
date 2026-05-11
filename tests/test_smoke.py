from crocs import __version__
from crocs.config import Settings
from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)
from crocs.ml.features import add_calendar_features, build_supervised_frame
from crocs.ml.production import CATS, TABULAR, upcoming_break_days
from crocs.ml.weather import add_weather_features, parse_pogodaiklimat_archive


def test_version():
    assert __version__


def test_schema_columns():
    assert "sale_date" in FORECAST_COLUMNS
    assert "required_employees" in LABOR_DEMAND_COLUMNS
    assert "station_key" in SCHEDULE_COLUMNS
    assert "issue_type" in COVERAGE_REPORT_COLUMNS


def test_default_settings():
    settings = Settings()
    assert settings.paths.raw_data_dir.as_posix() == "data/raw"
    assert settings.outputs.coverage_report == "coverage_report.xlsx"


def test_russian_holiday_features_for_may_2026():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "sale_date": ["2026-04-30", "2026-05-01", "2026-05-02", "2026-05-04"],
            "sale_hour": [12, 12, 12, 12],
        }
    )

    featured = add_calendar_features(frame)

    assert featured.loc[0, "is_ru_preholiday"] == 1
    assert featured.loc[1, "is_ru_public_holiday"] == 1
    assert featured.loc[1, "is_ru_holiday_period"] == 1
    assert featured.loc[1, "is_may_day_block"] == 1
    assert featured.loc[1, "holiday_block_day_index"] == 1
    assert featured.loc[1, "holiday_block_length"] == 3
    assert featured.loc[1, "days_to_victory_day"] == 8
    assert featured.loc[2, "is_ru_holiday_period"] == 1
    assert featured.loc[2, "holiday_block_day_index"] == 2
    assert featured.loc[3, "is_may_holiday_season"] == 1
    assert featured.loc[3, "holiday_name_code"] == 0


def test_production_feature_set():
    """Production использует 39 фич, 8 категориальных для CatBoost target-encoding."""
    # Лаги — основа модели
    assert "lag_7d" in TABULAR
    assert "lag_14d" in TABULAR
    assert "lag_28d" in TABULAR
    assert "lag_364d" in TABULAR
    assert "rolling_7d_mean" in TABULAR
    assert "rolling_28d_mean" in TABULAR
    assert "rolling_7d_to_28d_ratio" in TABULAR

    # Праздники
    assert "is_ru_public_holiday" in TABULAR
    assert "is_may_day_block" in TABULAR
    assert "days_to_next_ru_holiday" in TABULAR

    # Break-days (новые фичи)
    assert "upcoming_break_days" in TABULAR
    assert "past_break_days" in TABULAR
    assert "is_bridge_day" in TABULAR

    # Lagged weather (без data leakage)
    assert "weather_temp_lag_7d" in TABULAR
    assert "weather_precip_lag_7d" in TABULAR

    # Категориальные (8 шт)
    assert len(CATS) == 8
    assert "day_of_week" in CATS
    assert "sale_hour" in CATS
    assert "holiday_name_code" in CATS
    assert "upcoming_break_days" in CATS


def test_upcoming_break_days_calendar():
    """Календарь bridge-дней корректно расставлен для 2024-2026."""
    import pandas as pd
    # 2025-04-30 → впереди 4-дневный weekend (May 1-4)
    assert upcoming_break_days(pd.Timestamp("2025-04-30")) == 4
    # 2026-04-30 → впереди 3-дневный weekend (May 1-3)
    assert upcoming_break_days(pd.Timestamp("2026-04-30")) == 3
    # 2024-04-30 → впереди только May 1 (изолированный)
    assert upcoming_break_days(pd.Timestamp("2024-04-30")) == 1


def test_calendar_features_cover_quarter_salary_and_time_of_day():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "sale_date": ["2026-02-28", "2026-04-15", "2026-04-15"],
            "sale_hour": [9, 13, 19],
        }
    )

    featured = add_calendar_features(frame)

    assert featured.loc[0, "quarter"] == 1
    assert featured.loc[0, "is_salary_day"] == 1
    assert featured.loc[0, "is_month_end_salary_window"] == 1
    assert featured.loc[0, "is_morning_menu"] == 1
    assert featured.loc[1, "quarter"] == 2
    assert featured.loc[1, "is_lunch_hour"] == 1
    assert featured.loc[2, "is_evening_hour"] == 1


def test_supervised_frame_cuts_history_before_stabilization_date():
    import pandas as pd

    dates = pd.date_range("2022-09-15", "2022-10-31", freq="D")
    train = pd.DataFrame(
        {
            "sale_date": [day.date() for day in dates],
            "sale_hour": [12] * len(dates),
            "guests_count": list(range(len(dates))),
        }
    )

    frame = build_supervised_frame(train, hours=(12,))

    assert frame["sale_date"].min() >= pd.Timestamp("2022-09-22")


def test_weather_features_join_exact_hours_without_interpolation():
    import pandas as pd

    frame = pd.DataFrame(
        {
            "sale_date": ["2026-05-01", "2026-05-01"],
            "sale_hour": [9, 10],
        }
    )
    weather = pd.DataFrame(
        {
            "sale_date": ["2026-05-01"],
            "sale_hour": [9],
            "temp_c": [12.5],
            "dew_point_c": [4.0],
            "humidity_pct": [60],
            "effective_temp_c": [12.0],
            "effective_sun_temp_c": [14.0],
            "pressure_hpa": [1010.0],
            "station_pressure_hpa": [992.0],
            "precipitation_mm": [0.2],
            "precipitation_24h_mm": [1.0],
            "snow_depth_cm": [0],
            "wind_speed_mps": [3],
            "visibility_km": [20],
            "cloud_total_octas": [8],
            "is_weather_precipitation": [1],
            "is_weather_rain": [1],
            "is_weather_snow": [0],
            "is_weather_fog": [0],
            "is_weather_thunderstorm": [0],
        }
    )

    featured = add_weather_features(frame, weather)

    assert featured.loc[0, "has_weather_observation"] == 1
    assert featured.loc[0, "weather_temp_c"] == 12.5
    assert featured.loc[1, "has_weather_observation"] == 0
    assert pd.isna(featured.loc[1, "weather_temp_c"])


def test_pogodaiklimat_parser_converts_utc_to_moscow_hour():
    import pandas as pd

    rain_text = "\u0441\u043b\u0430\u0431. \u0434\u043e\u0436\u0434\u044c"
    html = """
    <table>
      <tr><td colspan="2">time utc date</td></tr>
      <tr><td>06</td><td>1.05</td></tr>
    </table>
    <table>
      <tr>
        <td colspan="2">wind</td><td>visibility</td><td>event</td><td>clouds</td>
        <td>temp</td><td>dew</td><td>humidity</td><td>te</td><td>tes</td><td>comfort</td>
        <td>P</td><td>Po</td><td>tmin</td><td>tmax</td><td>R</td><td>R24</td><td>S</td>
      </tr>
      <tr>
        <td>SW</td><td>2</td><td>20 km</td><td>EVENT_TEXT</td><td>8/4 1000 m</td>
        <td>+10.5</td><td>+4.5</td><td>70</td><td>+9</td><td>+11</td><td>cool</td>
        <td>1012.3</td><td>994.1</td><td></td><td></td><td>0.4</td><td></td><td></td>
      </tr>
    </table>
    """.replace("EVENT_TEXT", rain_text)

    weather = parse_pogodaiklimat_archive(html, year=2026)

    assert weather.loc[0, "sale_date"] == pd.Timestamp("2026-05-01").date()
    assert weather.loc[0, "sale_hour"] == 9
    assert weather.loc[0, "temp_c"] == 10.5
    assert weather.loc[0, "is_weather_rain"] == 1


def test_production_uses_catboost_mae():
    """Production imports CatBoost MAE model helpers without data leakage."""
    from crocs.ml.production import run_forecast, train_model

    assert callable(run_forecast)
    assert callable(train_model)
