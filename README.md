# crocs

Почасовой прогноз числа гостей (ML: CatBoost и др.).

## Структура

```text
scripts/run_pipeline.py    # python -m scripts.run_pipeline
data/raw/                  # train, опционально weather / weather_moscow
data/output/               # при guests_source=file — forecast.xlsx
artifacts/                 # xlsx; figures: 01, 02_schedule_gantt/, 03_staffing_coverage/, 04-06 png
src/crocs/
  api/  domain/  io/  services/  ml/  cli.py  config.py
tests/
```

## Установка и запуск

Подробная пошаговая инструкция, флаги CLI и **карта файлов в `artifacts/`** — в **[`docs/RUN.md`](docs/RUN.md)**.

- **Данные для ML:** **`data/raw/`** — `train.csv` / `.xlsx`, опционально `weather`. Другая папка: `--data-dir`.
- **Готовый прогноз из файла:** положите **`forecast.xlsx`** в **`data/output/`** (или задайте `--forecast-input-dir` / `paths.forecast_input_dir` в YAML). В конфиге **`forecast.guests_source: file`**.

Результаты — в **`artifacts/`** (`forecast.xlsx`, графики в **`figures/`** — см. **`docs/RUN.md`**).

При **`schedule.enabled: true`** в YAML (и в `data/raw/`: `reqlabor`, `sched`, `staff_limits`; опционально `station_priorities`) после прогноза считается почасовой спрос и **`schedule.xlsx`**: двухэтапная оптимизация **PuLP + CBC** — сначала часы по дням без привязки к станциям, затем внутри каждого дня почасовое назначение на **до двух приоритетных станций**; старт смены только на сетке **`schedule.shift_start_step_hours`** (по умолчанию каждые 2 часа от `open_hour`). Длительности смен — из `sched` (колонка `duration_hours` и др.) или значения по умолчанию 4/6/8 ч. Дополнительно **`schedule_by_day.xlsx`**: по одному листу на каждый день горизонта — матрица «станция × час» (`h07`…), в ячейках перечислены `employee_id` через запятую.

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
