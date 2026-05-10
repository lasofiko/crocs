# crocs

Прогноз гостей и расписание персонала (ТЗ кейса).

## Структура

```text
scripts/run_pipeline.py    # python -m scripts.run_pipeline
data/raw/                  # входные таблицы (см. data/raw/README.md)
artifacts/                 # forecast.xlsx, schedule.xlsx; подпапки figures/, demo/
src/crocs/
  domain/  io/  services/  ml/  cli.py  config.py
tests/
develop/ARCHITECTURE.md
```

## Установка и запуск

Входные таблицы по умолчанию читаются из **`data/raw/`** (имена: `train`, `reqlabor`, `sched`, `station_priorities`, `shifts`, `staff_limits` — расширение `.csv` или `.xlsx`). Другая папка: `python -m crocs --data-dir путь`.

Результаты пайплайна — в **`artifacts/`**.

```powershell
pip install -e ".[dev]"
python -m scripts.run_pipeline
```

Также: `python -m crocs`, `crocs-run`. Опционально ML: `pip install -e ".[dev,ml]"`. Проверка входов: `--check-only`.

## Тесты

```powershell
pytest -q
```
