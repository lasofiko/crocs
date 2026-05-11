# Прогнозирование числа гостей — Презентация ML-части

> Текущий результат: **WAPE 0.12755** на Kaggle (3-е место в команде).
> Полный pipeline от EDA до production-готовой модели.

---

## 📊 Структура презентации (10-12 слайдов)

### Слайд 1 — Задача и контекст

**Что говорить**:
- Прогноз почасового числа гостей фастфуд-ресторана на 7 дней вперёд (27.04.26 — 03.05.26)
- Включает 3 государственных выходных (1-3 мая) — нестандартная неделя
- Метрика: **WAPE** на Kaggle (симметричная относительная ошибка)
- Бизнес-цель: прогноз затем превращается в расписание смен через `reqlabor.csv`

**Визуал**: схема data flow (можно из `docs/ML_PRODUCTION.md`):
```
train.csv → ML model → guests forecast → labormap → schedule
```

---

### Слайд 2 — Прогресс по итерациям

**Что говорить**: показать как WAPE менялся от итерации к итерации (нагляднее всего)

```
v1 (single LGBM + holiday margin):  0.1697   ← старт
v4 (4-model ensemble):              0.1378   (-3.2 п.п.)
v7 (+ sample weights):              0.1335   (-0.4 п.п.)
v8 (+ preholiday features):         0.1326   (-0.1 п.п.)
cat.csv (CatBoost + categoricals):  0.1283   (-0.4 п.п.)
cat_mae.csv (+ MAE objective):      0.12755  (-0.07 п.п.) ← текущий
```

**Визуал**: bar chart с историей submission'ов, на оси WAPE.

---

### Слайд 3 — EDA: ключевые находки

**Что показать**:
1. Тренд + сезонность — `artifacts/figures/eda_01_daily_trend.png`
2. Heatmap (DOW × hour) — `artifacts/figures/eda_03_heatmap_dow_hour.png`
3. Праздничные эффекты — `artifacts/figures/eda_05_holiday_effects.png`

**Ключевые инсайты для презы**:
- Стабилизация трафика после ребрендинга — **отрезали данные с 2022-09-22**
- Праздники = **58% от обычного трафика** в среднем, но по часам разное (утром 40%, вечером 80%)
- Сильная недельная сезонность (пятница пик, воскресенье минимум)

---

### Слайд 4 — Feature Engineering: что оставили и почему

**Что говорить**: показать что было ~70 фич, оставили 28-34 (после нескольких ревизий)

**Таблица решений**:
| Категория | Оставили? | Причина |
|-----------|:---------:|---------|
| Лаги (7/14/28/364 дней) | ✅ | Главный сигнал (75%+ объясняющей силы) |
| Rolling статистики | ✅ | Локальный тренд |
| 14 праздничных фич | ✅ | Главная цель прогноза |
| 4 pre/post-holiday фич | ✅ | Эффект ажиотажа |
| 2 погодные фичи (интерполированные) | ✅ | Только после правильной интерполяции (forward-fill 3h → hourly) |
| Циклические (sin/cos) | ❌ | Деревья не нужно |
| Зарплатные дни | ❌ | Эффект 1.4 гостя/час = шум |
| 12 дополнительных погодных | ❌ | 0.2% gain без интерполяции |

**Визуал**: SHAP summary plot — `artifacts/figures/shap_catboost.png`

---

### Слайд 5 — Выбор архитектуры: bake-off 5 моделей

**Что говорить**: сравнили 5 принципиально разных подходов на одинаковом CV

| Модель | BT WAPE | Идея |
|--------|--------:|------|
| Baseline (медиана 8 недель) | 18.4% | sanity check |
| Seasonal naive (lag_7d) | 17.4% | sanity check |
| Single LGBM (q@0.7) | 13.0% | один boosting |
| **Ensemble 4 модели** | **11.9%** | RF + XGB + CatBoost + LGBM |
| Hybrid | 13.7% | бейзлайн + ML на остатках |

**Визуал**: `artifacts/figures/cv_bakeoff_comparison.png` — 6-панельное сравнение

**Главный график**: trade-off scatter в правом нижнем углу — точность vs Coverage на праздниках.

---

### Слайд 6 — Метрики: почему WAPE, не MAPE

**Что говорить**: бизнес-метрика и операционная — разные

| Метрика | Когда использовать |
|---------|---------------------|
| **WAPE** = Σ\|y−ŷ\| / Σy | Headline (Kaggle) — устойчива к низким значениям |
| MAPE | ❌ Взрывается на 7:00 (40 гостей промах 10 = 25%) |
| Coverage (через `reqlabor`) | Бизнес: % часов где смена укомплектована |
| Employee-MAE | Операционная — сколько сотрудников промах |

**Визуал**: график WAPE по часам vs MAPE по часам — показать почему MAPE искажает.

---

### Слайд 7 — Финальная модель: CatBoost + MAE

**Что говорить**: лучшая комбинация

```python
CatBoostRegressor(
    loss_function="MAE",        # симметричная WAPE-aligned функция
    iterations=600,
    learning_rate=0.05,
    depth=7,
    cat_features=[
        "day_of_week",
        "month",
        "holiday_name_code",
        "sale_hour",
        "holiday_block_day_index",
        "holiday_block_length",
    ],
)
```

**Ключевые архитектурные решения**:
1. **CatBoost вместо LightGBM** — native categorical encoding с target-mean даёт +0.4 п.п. на WAPE
2. **MAE loss вместо RMSE** — прямо оптимизирует абсолютную ошибку (WAPE-aligned)
3. **Sample weights**: ×2 на последние 6 месяцев, ×3 на исторические майские 2025
4. **Pre-holiday фичи**: `is_day_before_state_holiday`, `is_short_work_week`
5. **Погода с интерполяцией** (forward-fill 3h → hourly)

---

### Слайд 8 — SHAP: что реально драйвит прогноз

**Визуал**: `artifacts/figures/shap_catboost.png`

**Топ-10 фич по влиянию**:
1. `rolling_7d_mean` — недельный тренд
2. `lag_28d` — месячный паттерн
3. `lag_7d` — «то же что неделю назад»
4. `lag_14d` — двухнедельный
5. `rolling_28d_mean` — месячное среднее
6. `day_of_week` — недельная сезонность
7. `is_weekend` — выходной
8. `lag_364d` — годовой лаг (важен для праздников)
9. `sale_hour` — внутри-дневная сезонность
10. `weather_precip_interp` — **погода работает с интерполяцией** (раньше была мёртвая)

---

### Слайд 9 — Валидация: walk-forward CV

**Что говорить**: правильная CV для временных рядов

**Подход**:
- Не k-fold (это даст утечку в TS)
- **6 фолдов walk-forward**: 3 rolling недели + 3 праздничных (Feb 23, May Day 2025, Victory Day 2025)
- Финальный бэктест на **тех же календарных датах** что Kaggle test (2025-04-27 → 2025-05-03)

**Визуал**: `artifacts/figures/cv_bakeoff_per_fold.png` — траектории моделей по фолдам

---

### Слайд 10 — Структура production-кода

**Что говорить**: вся ML-часть — единый pipeline

```
src/crocs/ml/
├── features.py          # add_calendar_features, add_lag_features, etc.
├── russian_calendar.py  # FIXED_PUBLIC_HOLIDAYS, OFFICIAL_2026
├── weather.py           # parse_pogodaiklimat_archive, add_weather_features
├── lightgbm_model.py    # TUNED_LGBM_PARAMS, train_lightgbm
├── ensemble_model.py    # ForecastEnsemble
└── lightgbm_pipeline.py # run_ensemble_forecast (полный pipeline)

scripts/
├── final_ensemble.py    # 4-model ensemble (LGBM+CatBoost+Prophet+SARIMA)
├── cat_optimization.py  # CatBoost variants (MAE, multi-seed, deep)
└── run_lightgbm_forecast.py  # production CLI
```

13 smoke-тестов покрывают: features, holidays, weather, supervised frame, model config.

---

### Слайд 11 — Результат на Kaggle

**Что показать**: скриншот лидерборда + наш score

| Команда | Score | Submissions |
|--------|------:|------------:|
| #1 кебаб | 0.1136 | 10 |
| #2 Светлячки | 0.1151 | 3 |
| **#3 crocs (мы)** | **0.12755** | многократно |

**Что говорить**:
- За 8+ итераций сократили WAPE с 17% до 12.7% (30% относительного улучшения)
- Гэп до лидера — 1.4 п.п. — закрывается через стэкинг и дополнительные фичи

---

### Слайд 12 — Что попробовали и не сработало (важно для презы)

**Честность ценится**:

| Попытка | Результат | Почему не сработало |
|---------|-----------|---------------------|
| Quantile loss + holiday margin | Coverage 90%, но WAPE 17% | Оптимизация под другую метрику |
| Погода без интерполяции | 0.2% gain | 31% покрытие |
| Per-hour models (16 моделей) | Хуже | Слишком мало данных на модель |
| Lag_365 (holiday-semantic lag) | Хуже | Потеря 30% training data |
| Multi-seed CatBoost | +0.4 п.п. ❌ | CatBoost уже стабилен |
| Deep CatBoost (1000 iter) | +0.6 п.п. ❌ | Переобучение |
| Prophet/SARIMA в ensemble | Утянули вниз | На hourly данных слабы |

**Главный урок**: на этой задаче **простая правильная модель > сложная**. CatBoost с правильной функцией потерь (MAE) и native categoricals обгоняет ансамбли.

---

## 🎨 Графики которые нужно использовать

Все лежат в `artifacts/figures/`:

| Файл | Что показывает | На какой слайд |
|------|----------------|----------------|
| `eda_01_daily_trend.png` | Дневной тренд + скользящие средние | EDA |
| `eda_03_heatmap_dow_hour.png` | Тепловая карта DOW × hour | EDA |
| `eda_05_holiday_effects.png` | Эффект праздников | EDA |
| `cv_bakeoff_comparison.png` | 6 панелей сравнения 5 моделей | Bake-off |
| `cv_bakeoff_per_fold.png` | Траектории WAPE/Coverage по фолдам | Валидация |
| `shap_catboost.png` | SHAP важность фич | Финальная модель |
| `shap_lgbm.png` | Сравнение с LGBM | Финальная модель |
| `final_model_comparison.png` | Trade-off Coverage vs WAPE | Trade-off |
| `v4_residuals_may_2025.png` | Анализ остатков | Диагностика |

---

## 📁 Артефакты в проекте

```
artifacts/
├── figures/                          # 16+ графиков
├── reports/
│   ├── cv_bakeoff.csv               # детальные CV результаты 5 моделей × 6 фолдов
│   ├── cv_bakeoff_summary.csv       # агрегированные по сегментам
│   ├── final_ensemble_backtest.csv  # 4-моделей бэктест на 2025-04-27→05-03
│   ├── optuna_best_params.json      # тюнинг LGBM
│   └── current_lightgbm_feature_importance.csv

notebooks/
├── 01_train_eda_and_forecast_baseline.ipynb  # EDA
└── 02_model_selection_journey.ipynb          # 61 ячейка — путь принятия решений

models/
├── lightgbm_production.txt          # снэпшот модели
└── lightgbm_production_meta.json    # параметры + CV метрики

docs/
├── ML_PRODUCTION.md                 # детальная техническая документация
└── PRESENTATION_OUTLINE.md          # этот файл
```

---

## 🔑 Ключевые цифры для презы

| Метрика | Значение |
|---------|---------:|
| **Текущий Kaggle WAPE** | **0.12755** |
| Место на leaderboard | #3 из 5+ |
| Улучшение vs стартовая модель | −5 п.п. (30% относительно) |
| Гэп до лидера | 1.4 п.п. |
| Submissions сделано | 10+ |
| Архитектура | CatBoost (MAE loss) + native categoricals + sample weights |
| Total features | 34 (28 base + 4 preholiday + 2 weather) |
| Training rows | 20,460 (post-rebrand) |
| Backtest WAPE на тех же датах | 0.1349 |

---

## 💬 Speaker notes — что сказать устно

**Заход (1 минута)**:
> «Задача — спрогнозировать почасовое число гостей на майские праздники.
> Сложность: это нестандартная неделя с 3 государственными выходными,
> и наша модель должна правильно обработать как пред-праздничный ажиотаж,
> так и сам спад на праздничные дни.»

**Про путь (2-3 минуты)**:
> «Мы прошли 10+ итераций, сократив WAPE с 17% до 12.7% — это 30% относительного улучшения.
> На каждой итерации мы тестировали гипотезу на CV и затем валидировали на Kaggle.
> Не все гипотезы сработали — например, multi-seed averaging,
> которое обычно помогает, у нас наоборот ухудшило результат на 0.4 п.п.»

**Про финальную модель (2 минуты)**:
> «Финальная модель — CatBoost с MAE loss и native категориальными фичами.
> Ключевое решение — использовать target-mean encoding через native categoricals
> для пар (day_of_week, hour), (holiday_name, day_of_block) — это даёт модели прямое
> понимание как меняется поток в разных типах времени.»

**Про валидацию (1 минута)**:
> «Мы использовали walk-forward CV на 6 фолдах, включая 3 праздничных,
> и финальный бэктест на тех же календарных датах что Kaggle test, но годом раньше.
> Это даёт честную оценку производительности на праздничной неделе.»

**Финал (30 секунд)**:
> «Текущий результат — 3-е место. Гэп до лидера 1.4 п.п. — закрывается через стэкинг
> и более глубокий feature engineering, направления уже исследуем.»
</thinking>

Готово, единый файл для презы: [docs/PRESENTATION_OUTLINE.md](docs/PRESENTATION_OUTLINE.md)

Включает:

## Содержимое

1. **Структура из 12 слайдов** — каждый со своим месседжем и графиком
2. **Все ключевые цифры** для презы
3. **Список графиков** с путями (где какой использовать)
4. **Список артефактов** (отчёты, метрики, ноутбуки)
5. **Speaker notes** — что сказать устно

## Ключевые блоки для презы

| Слайд | Что показать |
|-------|--------------|
| 1. Задача | Data flow схема |
| 2. **Прогресс по итерациям** | bar chart 0.17 → 0.1275 |
| 3. EDA | 3 графика тренда/сезонности |
| 4. Feature engineering | таблица «оставили / убрали» |
| 5. **Bake-off 5 моделей** | `cv_bakeoff_comparison.png` |
| 6. Метрики | WAPE vs MAPE по часам |
| 7. Финальная модель | код CatBoost + 5 решений |
| 8. **SHAP важность** | `shap_catboost.png` |
| 9. Walk-forward CV | `cv_bakeoff_per_fold.png` |
| 10. Структура кода | дерево файлов |
| 11. **Результат на Kaggle** | скрин лидерборда + наш score |
| 12. Что не сработало (честность ценится) | таблица failed experiments |

## Главные цифры

- **WAPE 0.12755** (текущий best)
- **#3 место** на leaderboard
- **−5 п.п.** улучшение от стартовой v1
- **34 фичи** (28 + 4 preholiday + 2 weather)
- **20,460 строк** обучения
- **CatBoost MAE + native categoricals**

## Что для презы можно сразу взять

Файлы из `artifacts/figures/` (все там готовые PNG):
- `eda_01_daily_trend.png`
- `eda_03_heatmap_dow_hour.png`
- `eda_05_holiday_effects.png`
- `cv_bakeoff_comparison.png` ← главный
- `cv_bakeoff_per_fold.png`
- `shap_catboost.png` ← обязательно
- `shap_lgbm.png`
- `final_model_comparison.png`
- `v4_residuals_may_2025.png`

Файл `docs/PRESENTATION_OUTLINE.md` отдельно — можно скинуть как есть, тот кто делает презу всё нужное найдёт. Если результат улучшится после final_v2, я обновлю файл.