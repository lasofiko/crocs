# Подробный запуск crocs: команды и где смотреть результаты

Документ описывает запуск из **корня репозитория** (папка `crocs`, где лежат `pyproject.toml`, `configs/`, `data/`, `artifacts/`). ОС: Windows PowerShell; на Linux/macOS команды те же, пути замените на свои.

---

## 1. Установка

```powershell
cd C:\Users\Соня\python\PycharmProjects\crocs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

Проверка:

```powershell
python -m crocs --help
```

(Эквивалент: команда `crocs-run` из того же окружения.)

---

## 2. Что должно лежать на диске до запуска

### 2.1. Конфиг

- **`configs/default.yaml`** — окно прогноза (`forecast.start` / `end`), часы ресторана (`open_hour`, `close_hour`), источник гостей (`forecast.guests_source`: `file` или `model`), пути и имена выходных файлов, блок **`schedule`** (вкл/выкл и параметры PuLP).

### 2.2. Вход: готовый прогноз гостей (`guests_source: file`)

- Каталог из YAML: **`paths.forecast_input_dir`** (часто `data/output/`).
- Файл: **`outputs.forecast`** из YAML (часто **`forecast.xlsx`**).
- Колонки в таблице: **`sale_date`**, **`sale_hour`**, **`guests_count`** (регистр имён при чтении нормализуется).

### 2.3. Вход: ML-прогноз (`guests_source: model`)

- В **`paths.raw_data_dir`** (по умолчанию **`data/raw/`**): **`train.csv`** или **`train.xlsx`**.
- Опционально: **`weather.csv`** / **`weather_moscow.csv`** (или `.xlsx`).

### 2.4. Расписание (`schedule.enabled: true`)

В **`data/raw/`** (или в каталоге из `--data-dir`):

| Файл | Назначение |
|------|------------|
| **`reqlabor.csv`** / **`.xlsx`** | Спрос по станциям от числа гостей: `station_key`, `version`, `guests_count`, `reqlabor` |
| **`sched.csv`** / **`.xlsx`** | Длительности смен: колонка вроде **`duration_hours`** (или `duration`, `hours`, `len_hours`); иначе берутся 4/6/8 ч |
| **`staff_limits.csv`** / **`.xlsx`** | **`employee_id`**, лимит недели: **`max_weekly_hours`** или **`worktime_limit`** (и др. см. код) |
| **`station_priorities`** (опционально) | **`station_key`**, при наличии **`priority`** (меньше — важнее) |

---

## 3. Команды запуска

Все пути ниже — **относительно корня проекта**, если вы уже сделали `cd` в `crocs`.

### 3.1. Только проверка входов (без записи артефактов)

```powershell
python -m crocs --check-only
```

Проверяются: наличие нужных таблиц, читаемость `forecast.xlsx` (при `guests_source: file`), и т.д. В конце печатается **`OK`**, код выхода **0**.

### 3.2. Полный прогон (типичный пример)

```powershell
python -m crocs `
  --data-dir data/raw `
  --forecast-input-dir data/output `
  --artifacts-dir artifacts `
  --config configs/default.yaml
```

Одной строкой:

```powershell
python -m crocs --data-dir data/raw --forecast-input-dir data/output --artifacts-dir artifacts --config configs/default.yaml
```

### 3.3. Полезные флаги

| Флаг | Значение |
|------|----------|
| `--data-dir` | Каталог с `train`, `reqlabor`, `sched`, … (по умолчанию `data/raw`) |
| `--forecast-input-dir` | Где лежит входной **`forecast.xlsx`** при `guests_source: file` (алиас: `--schedule-input-dir`) |
| `--artifacts-dir` | Куда писать результаты (по умолчанию **`artifacts`**) |
| `--config` | YAML-конфиг; если не указан, используется **`configs/default.yaml`** от **текущей рабочей директории** |
| `--guests-source` | `file` или `model` — переопределяет YAML, если указан |
| `--convert-xlsx-to-csv` | Конвертирует часть xlsx в csv в `--data-dir` (служебно) |

### 3.4. Тесты

```powershell
pytest -q
```

---

## 4. Куда что записывается (карта артефактов)

Корень выхода задаётся **`--artifacts-dir`** (ниже для примера **`artifacts/`**). Имена файлов можно переименовать в YAML в секции **`outputs`**.

### 4.1. Всегда (любой успешный прогон с прогнозом)

| Путь | Что внутри |
|------|------------|
| **`artifacts/forecast.xlsx`** | Почасовой прогноз гостей за окно из конфига (те же колонки, что для ML/файла). |
| **`artifacts/figures/01_forecast_guests.png`** | График: ось X — дата/час, Y — число гостей. |

### 4.2. Если `schedule.enabled: true` и данные для расписания прошли проверку

Параметры в YAML (секция **`schedule`**):

- **`max_priority_stations: 0`** — в PuLP участвуют **все станции** из почасового спроса (иначе — не больше N станций по приоритету/спросу).
- **`min_staff_per_station`** (по умолчанию **2**) — при ненулевом спросе на (станция, час) целевое покрытие не ниже этого числа (см. **`min_staff_only_when_demand`**).

| Путь | Что внутри |
|------|------------|
| **`artifacts/schedule.xlsx`** | Интервалы смен: `ds`, `station_key`, `employee_id`, `starttime`, `finishtime`. |
| **`artifacts/schedule_by_day.xlsx`** | Книга Excel: **один лист на календарный день** горизонта (имя листа `YYYY-MM-DD`). На листе: строки — **станции** (все из спроса), столбцы **`h07`…** (часы ресторана), в ячейках — **`employee_id` через запятую** (если несколько человек в час на станции). |
| **`artifacts/figures/02_schedule_gantt/gantt.png`** | Диаграмма **Ганта**: по вертикали сотрудники, по горизонтали время, цвет — станция. |
| **`artifacts/figures/03_staffing_coverage/coverage.png`** | **Тепловая карта** «станция × время»: `назначено − требование` (красный — недобор относительно спроса и `min_staff_per_station`). |
| **`artifacts/figures/04_hourly_station_demand.png`** | Линии: почасовой **спрос по станциям** (после `reqlabor`). |
| **`artifacts/figures/05_schedule_assigned_by_station.png`** | Линии: сколько человек **фактически назначено** по станциям и часам (из решения PuLP). |
| **`artifacts/figures/06_total_demand_vs_assigned.png`** | Две линии: **сумма спроса** по всем станциям и **сумма человеко-часов** назначений по часам. |

Если при отрисовке произошла ошибка, сообщение попадёт в **warnings** в консоли (строка вида `графики не сохранены: …`), остальные этапы пайплайна могли завершиться успешно.

### 4.3. Чего нет в `artifacts/` по умолчанию

- Промежуточная таблица **почасового спроса по станциям** на диск **отдельным файлом не пишется** (она есть во внутренних данных и в графике **04**). Если нужен экспорт — это отдельная доработка.

---

## 5. Как «посмотреть» результаты

1. **Таблицы** — открыть в Excel **`artifacts/forecast.xlsx`**, при расписании ещё **`schedule.xlsx`** и **`schedule_by_day.xlsx`**.
2. **Картинки** — проводник Windows: папка **`artifacts/figures/`**, просмотр PNG двойным щелчком или встроенным просмотрщиком.
3. **Лог в консоли** — этапы: проверка входов → прогноз → (при schedule) спрос → PuLP → запись файлов → графики → **`Done`**. Код выхода **0** = успех.

---

## 6. Типичные ошибки

- **`DataValidationError`** — нет файла, нет колонки, пустой прогноз после фильтра по датам/часам.
- **`ScheduleError`** — PuLP/CBC не нашёл допустимое решение или нет старта смены на заданной сетке часов.

Тогда исправьте входные таблицы или параметры в **`configs/default.yaml`** (`schedule`, `forecast`, лимиты сотрудников, длительности смен).

---

## 7. Где смотреть код пайплайна

- Точка входа CLI: **`src/crocs/cli.py`**
- Сборка шагов: **`src/crocs/services/pipeline_service.py`**
- Графики: **`src/crocs/viz/report_figures.py`**
- Расписание PuLP: **`src/crocs/services/schedule_pulp.py`**
- Таблицы по дням: **`src/crocs/services/schedule_station_hour_tables.py`**
