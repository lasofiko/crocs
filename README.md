# crocs

Прогноз гостей и расписание персонала (ТЗ кейса).

## Структура

```text
scripts/run_pipeline.py    # python -m scripts.run_pipeline
data/raw/                  # ML и спрос: train, reqlabor, weather
data/output/               # только оптимизация расписания: sched, station_priorities, shifts, staff_limits
artifacts/                 # forecast.xlsx, schedule.xlsx; подпапки figures/, demo/
src/crocs/
  api/  domain/  io/  services/  ml/  cli.py  config.py
tests/
develop/ARCHITECTURE.md
```

## Установка и запуск

- **ML и почасовой спрос:** **`data/raw/`** — `train`, `reqlabor`, опционально `weather` / `weather_moscow` (`.csv` или `.xlsx`). Другая папка: `--data-dir`.
- **Только солвер расписания:** **`data/output/`** — `sched`, `station_priorities`, `shifts`, `staff_limits`. Другая папка: `--schedule-input-dir` или `paths.schedule_input_dir` в YAML.

Результаты пайплайна — в **`artifacts/`**.

```powershell
pip install -e ".[dev]"
python -m scripts.run_pipeline
```

Также: `python -m crocs`, `crocs-run`. Опционально ML: `pip install -e ".[dev,ml]"`. Проверка входов: `--check-only`.

После `run_pipeline` витрина расписания для фронта `schedule-animation/`: `crocs-api` (по умолчанию `http://127.0.0.1:8000`, читает `artifacts/schedule.xlsx` и `artifacts/forecast.xlsx`). Переменная `CROCS_ARTIFACTS_DIR` задаёт другую папку. В dev фронта прокси Vite шлёт `/api` на этот хост; `VITE_API_URL` можно не задавать.

## Тесты

```powershell
pytest -q
```
