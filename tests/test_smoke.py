from crocs import __version__
from crocs.config import Settings
from crocs.domain.models import (
    COVERAGE_REPORT_COLUMNS,
    FORECAST_COLUMNS,
    LABOR_DEMAND_COLUMNS,
    SCHEDULE_COLUMNS,
)


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
