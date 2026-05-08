# crocs

Прогноз гостей по часам и автоматическое расписание персонала по станциям (кейс ресторана).

## Структура

```text
crocs/
  pyproject.toml
  data/raw/           # входные CSV из ТЗ (не коммитим по умолчанию)
  output/             # forecast.xlsx, schedule.xlsx, figures/, demo/
  notebooks/          # опционально EDA
  develop/
    ARCHITECTURE.md   # описание архитектуры и пайплайна
  src/crocs/
    main.py           # CLI
    pipeline.py       # оркестрация шагов
    config.py         # даты и часы ресторана
    schemas.py        # имена колонок Excel по ТЗ
    io/               # загрузка CSV, запись xlsx
    forecast/         # ML-прогноз гостей
    demand/           # гости → потребность по станциям
    scheduling/       # OR-Tools CP-SAT
    quality/          # проверка ограничений ТЗ
    viz/              # графики и демо
  tests/
```

## Установка

```powershell
cd C:\Users\Соня\python\PycharmProjects\crocs
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
```

ML-зависимости опционально: `pip install -e ".[dev,ml]"`.

## Запуск

Положите входные таблицы в `data/raw/` — для каждой допустим **CSV или Excel** с тем же именем (например `train.xlsx` или `train.csv`; если оба есть, читается CSV). Затем:

```powershell
python -m crocs
```

Проверка, что все входные файлы на месте:

```powershell
python -m crocs --check-only
```

После реализации `forecast`, `demand` и `scheduling` в `output/` появятся `forecast.xlsx` и `schedule.xlsx`.

## Тесты

```powershell
pytest -q
```

## Документация

Подробная архитектура: [develop/ARCHITECTURE.md](develop/ARCHITECTURE.md).
