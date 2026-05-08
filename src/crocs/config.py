"""Константы периода и часов работы ресторана по ТЗ."""

from datetime import date

# Прогноз на неделю кейса (подставьте актуальные даты из финального ТЗ при необходимости)
FORECAST_START: date = date(2026, 4, 27)
FORECAST_END: date = date(2026, 5, 3)

RESTAURANT_OPEN_HOUR = 7
RESTAURANT_CLOSE_HOUR = 23  # последний час интервала [7..23] включительно — уточните по ТЗ
