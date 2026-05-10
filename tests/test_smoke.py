from crocs import __version__
from crocs.config import Settings
from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)
from crocs.ml.features import add_calendar_features, build_supervised_frame
from crocs.ml.lightgbm_model import FEATURE_COLUMNS


def test_version():
    assert __version__


def test_schema_columns():
    assert "sale_date" in FORECAST_COLUMNS
    assert "required_employees" in LABOR_DEMAND_COLUMNS
    assert "station_key" in SCHEDULE_COLUMNS
    assert "issue_type" in COVERAGE_REPORT_COLUMNS


def test_default_settings():
    settings = Settings()
    assert settings.paths.raw_data_dir.as_posix() == "data/output"
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


def test_model_feature_set_uses_short_lags_and_salary_features():
    assert "lag_7d" in FEATURE_COLUMNS
    assert "lag_14d" in FEATURE_COLUMNS
    assert "lag_28d" in FEATURE_COLUMNS
    assert "lag_56d" not in FEATURE_COLUMNS
    assert "lag_91d" not in FEATURE_COLUMNS
    assert "lag_182d" not in FEATURE_COLUMNS
    assert "lag_364d" not in FEATURE_COLUMNS
    assert "is_salary_day" in FEATURE_COLUMNS
    assert "is_salary_window_2d" in FEATURE_COLUMNS
    assert "days_to_salary_day" in FEATURE_COLUMNS
    assert "quarter" in FEATURE_COLUMNS
    assert "hour_sin" in FEATURE_COLUMNS
    assert "dow_cos" in FEATURE_COLUMNS
    assert "daily_guests_lag_7d" in FEATURE_COLUMNS
    assert "daily_guests_rolling_28d_mean" in FEATURE_COLUMNS


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
