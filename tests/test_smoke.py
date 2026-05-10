from crocs import __version__
from crocs.config import Settings
from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)
from crocs.ml.features import add_calendar_features


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
