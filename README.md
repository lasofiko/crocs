# Crocs

**Crocs** — инструментарий для ресторанной аналитики: почасовой **прогноз числа гостей** (ML: CatBoost, LightGBM, XGBoost, Prophet и др.) и **планирование смен** с учётом спроса по станциям, лимитов сотрудников и бизнес-ограничений. Оптимизация расписания строится на **Google OR-Tools CP-SAT** с опциональным **LNS** (large neighborhood search) для улучшения качества решения.

Проект объединяет:

- **Python-пакет** `crocs` — CLI, сервисы пайплайна, ML, экспорт в Excel/SQLite, HTTP API на **FastAPI**;
- **`schedule-animation/`** — одностраничное приложение **React + Vite** для наглядного просмотра расписания и анимации (данные из статики `public/` или с бэкенда через прокси).

---

## Содержание

- [Возможности](#возможности)
- [Структура репозитория](#структура-репозитория)
- [Требования](#требования)
- [Быстрый старт](#быстрый-старт)
- [Подробный запуск пайплайна](#подробный-запуск-пайплайна)
- [HTTP API](#http-api)
- [Фронтенд `schedule-animation`](#фронтенд-schedule-animation)
- [Конфигурация и переменные окружения](#конфигурация-и-переменные-окружения)
- [Тесты и качество кода](#тесты-и-качество-кода)

---

## Возможности

| Область | Что делает система |
|--------|---------------------|
| **Прогноз гостей** | Обучение/инференс по истории (`train`), опционально погода; либо чтение готового `forecast.xlsx` из каталога (`guests_source: file`). |
| **Спрос по труду** | Пересчёт почасовой потребности по станциям из `reqlabor` и прогноза гостей. |
| **Расписание** | Назначение смен на горизонт с ограничениями из `sched`, `staff_limits`, приоритетов станций; кэш и история прогонов в **SQLite** (`artifacts/schedule_runs.db` по умолчанию). |
| **Артефакты** | Excel с прогнозом и сменами, отчётные графики в `artifacts/figures/` (см. [`docs/RUN.md`](docs/RUN.md)). |
| **Интеграция** | REST API для прогона пайплайна, фоновых задач и выдачи сохранённого расписания в JSON для фронта. |

---

## Структура репозитория

```text
configs/default.yaml       # Основной YAML: окно прогноза, пути, schedule, runtime
data/raw/                  # Входные таблицы: train, reqlabor, sched, staff_limits, …
data/output/               # Готовый прогноз при guests_source: file (forecast.xlsx)
artifacts/                 # Результаты: forecast.xlsx, schedule.xlsx, figures/, schedule_runs.db
docs/RUN.md                # Пошаговый запуск, флаги CLI, карта файлов в artifacts/
schedule-animation/        # React + Vite: анимация и дашборд расписания
scripts/                   # Вспомогательные скрипты (погода, отчёты, …)
src/crocs/                 # Исходный код пакета: api, cli, config, domain, io, ml, services, viz
tests/                     # Pytest
pyproject.toml             # Зависимости, entry points, ruff/pyright/pytest
```

Точки входа из `pyproject.toml`:

| Команда | Назначение |
|---------|------------|
| `crocs` / `crocs-run` | CLI пайплайна (`python -m crocs`). |
| `crocs-api-main` | HTTP API «полный» (`ForecastPipeline`, задачи, чтение расписания из БД). |
| `crocs-api` | Альтернативная точка входа API (см. `crocs.api.app`). |

---

## Требования

- **Python 3.12+** (см. `requires-python` в `pyproject.toml`).
- **Node.js 20+** (рекомендуется LTS) — только для каталога `schedule-animation/`.
- Достаточно места на диске под артефакты и, при необходимости, модели/кэш.

Установка зависимостей Python — через **pip** или совместимый менеджер; в документации ниже используется классический **venv**.

---

## Быстрый старт

### 1. Клонирование и виртуальное окружение

**Windows (PowerShell):**

```powershell
cd путь\к\crocs
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

**Linux / macOS:**

```bash
cd /path/to/crocs
python3.12 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
```

Проверка CLI:

```powershell
python -m crocs --help
```

### 2. Минимальный прогон пайплайна

Убедитесь, что в `configs/default.yaml` заданы корректные `forecast`, `paths` и при необходимости `scheduling`. Положите данные в `data/raw/` (и при `guests_source: file` — `forecast.xlsx` в каталог из `paths.forecast_input_dir`).

```powershell
python -m crocs --check-only
python -m crocs --data-dir data/raw --forecast-input-dir data/output --artifacts-dir artifacts --config configs/default.yaml
```

После успешного завершения смотрите `artifacts/` и раздел «Карта артефактов» в **[`docs/RUN.md`](docs/RUN.md)**.

### 3. API и фронт (локально)

В **одном** терминале из корня репозитория (чтобы относительные пути к конфигу и БД совпали с ожиданиями):

```powershell
crocs-api-main
```

По умолчанию сервер слушает **`http://127.0.0.1:8000`**. Документация интерактивно: **`http://127.0.0.1:8000/docs`**.

Во **втором** терминале:

```powershell
cd schedule-animation
npm ci
npm run dev
```

Vite поднимет dev-сервер (обычно порт **5173**) и **проксирует** запросы с префиксом `/api` на `http://127.0.0.1:8000` (см. `schedule-animation/vite.config.ts`). Откройте в браузере URL, который выведет Vite.

---

## Подробный запуск пайплайна

Флаги CLI, состав входных таблиц для расписания, типичные ошибки и **полная карта файлов в `artifacts/`** описаны в отдельном документе:

**[docs/RUN.md](docs/RUN.md)**

Кратко:

- **`forecast.guests_source: model`** — нужны `train` в `data/raw/` (и опционально погода).
- **`forecast.guests_source: file`** — нужен готовый файл прогноза (часто `data/output/forecast.xlsx`) с колонками вроде **`sale_date`**, **`sale_hour`**, **`guests_count`**.
- **`scheduling.enabled: true`** — в сырье должны быть таблицы для спроса и ограничений (`reqlabor`, `sched`, `staff_limits`, опционально `station_priorities`); имена файлов настраиваются в YAML.

---

## HTTP API

Запуск: **`crocs-api-main`** (или `python -m crocs.api.main`).

| Переменная | Значение по умолчанию | Смысл |
|------------|------------------------|--------|
| `CROCS_API_HOST` | `127.0.0.1` | Хост uvicorn. |
| `CROCS_API_PORT` | `8000` | Порт. |
| `CROCS_CONFIG` | `configs/default.yaml` | Путь к YAML относительно **текущей рабочей директории** процесса (или абсолютный путь). |
| `CROCS_CORS_ORIGINS` | `*` | Список origin через запятую для CORS. |

Основные маршруты (`src/crocs/api/main.py`):

| Метод и путь | Описание |
|--------------|----------|
| `GET /health` | Служебный статус, путь к конфигу, флаги preload. |
| `GET /api/v1/forecast-pipeline` | Синхронный прогон пайплайна; в ответе JSON с рядами прогноза, смен и спроса (см. модели ответа в OpenAPI `/docs`). |
| `GET /api/v1/schedule-runs/latest` | Последний сохранённый прогон с назначениями из SQLite (`runtime.schedule_db_path`). |
| `GET /api/v1/schedule-runs/{run_id}` | То же для конкретного `run_id`. |
| `POST /api/v1/pipeline/jobs` | Асинхронная постановка задачи пайплайна (**202** + `job_id`). |
| `GET /api/v1/pipeline/jobs/{job_id}` | Статус фоновой задачи. |

База прогонов задаётся в YAML: **`runtime.schedule_db_path`** (по умолчанию `artifacts/schedule_runs.db`). Пока не было успешного прогона с записью в БД, эндпоинты чтения расписания вернут **404** с пояснением в `detail`.

---

## Фронтенд `schedule-animation`

Стек: **React 19**, **TypeScript**, **Vite 8**, **Bootstrap 5**, **TanStack Query**, чтение XLSX через **SheetJS**.

| Команда | Действие |
|---------|----------|
| `npm ci` | Установка зависимостей по lock-файлу. |
| `npm run dev` | Режим разработки + прокси `/api` → бэкенд. |
| `npm run build` | Production-сборка в `dist/`. |
| `npm run preview` | Локальный просмотр сборки (прокси к API сохраняется). |

Переменные окружения (префикс Vite — **`VITE_`**), при необходимости в `.env` внутри `schedule-animation/`:

| Переменная | Назначение |
|------------|------------|
| `VITE_API_URL` | Базовый URL API, если фронт открыт не через Vite-прокси (иначе можно оставить пустым). |
| `VITE_SCHEDULE_PAGE_SIZE` | Размер страницы при запросе порций расписания (число, по умолчанию в коде 150). |

Статические демо-файлы лежат в **`schedule-animation/public/`** (`schedule.xlsx`, `staffing_requirements.xlsx` и др.) — приложение может работать с ними без бэкенда.

---

## Конфигурация и переменные окружения

- Основной файл настроек: **`configs/default.yaml`**. Секции типично включают `project`, `paths`, `inputs`, `outputs`, `forecast`, `scheduling`, `runtime`.
- Поверх YAML действуют переменные с префиксом **`CROCS_`** и вложенностью через **`__`** (см. `pydantic-settings` в `src/crocs/config.py`), например: `CROCS_FORECAST__GUESTS_SOURCE=file`.

Путь к БД расписания (для API и кэша прогонов):

```yaml
runtime:
  schedule_db_path: artifacts/schedule_runs.db   # или null — не писать в SQLite
```

---

## Тесты и качество кода

```powershell
pytest -q
```

Дополнительно (из dev-зависимостей):

```powershell
ruff check src tests scripts
pyright
```

---

## Документация и ссылки

| Ресурс | Содержание |
|--------|------------|
| [docs/RUN.md](docs/RUN.md) | Детальный запуск, флаги, артефакты, типичные ошибки. |
| `/docs` на запущенном API | OpenAPI/Swagger для всех маршрутов. |

Если вы расширяете пайплайн или API, имеет смысл обновлять **`docs/RUN.md`** вместе с изменением поведения CLI и путей артефактов.
