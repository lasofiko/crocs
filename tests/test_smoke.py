from crocs import __version__
from crocs.domain.models import FORECAST_COLUMNS, SCHEDULE_COLUMNS


def test_version():
    assert __version__


def test_schema_columns():
    assert "sale_date" in FORECAST_COLUMNS
    assert "station_key" in SCHEDULE_COLUMNS
