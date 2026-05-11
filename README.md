# crocs

Почасовой прогноз числа гостей (ML: CatBoost и др.).

## Структура

```text
scripts/run_pipeline.py    # python -m scripts.run_pipeline
data/raw/                  # train, опционально weather / weather_moscow
data/output/               # при guests_source=file — forecast.xlsx
artifacts/                 # forecast.xlsx, подпапка figures/
src/crocs/
  api/  domain/  io/  services/  ml/  cli.py  config.py
tests/
```

## Установка и запуск

- **Данные для ML:** **`data/raw/`** — `train.csv` / `.xlsx`, опционально `weather`. Другая папка: `--data-dir`.
- **Готовый прогноз из файла:** положите **`forecast.xlsx`** в **`data/output/`** (или задайте `--forecast-input-dir` / `paths.forecast_input_dir` в YAML). В конфиге **`forecast.guests_source: file`**.

Результаты — в **`artifacts/`** (`forecast.xlsx`, график `figures/01_forecast_guests.png`).

```powershell
pip install -e ".[dev]"
python -m crocs
```

Также: `crocs-run`. Проверка входов: `python -m crocs --check-only`.

HTTP API прогноза: `crocs-api-main` → эндпоинт **`GET /api/v1/forecast-pipeline`** (см. `src/crocs/api/main.py`).

## Тесты

```powershell
pytest -q
```
