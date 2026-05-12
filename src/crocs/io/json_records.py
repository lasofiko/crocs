"""Сериализация pandas DataFrame в JSON-совместимые списки словарей (для API и фронта)."""

from __future__ import annotations

import json
from typing import Any

import pandas as pd


def dataframe_to_json_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Даты в ISO, NaN → null; подходит для ответа FastAPI/JSON."""
    if df is None or df.empty:
        return []
    blob = df.to_json(orient="records", date_format="iso")
    return json.loads(blob)
