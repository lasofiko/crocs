# ML-часть проекта — production state

Краткая справка для тех, кто будет работать с прогнозной моделью гостей.

## Что в проде

**Модель**: Single LightGBM, objective `quantile`, alpha=0.7
**Гиперпараметры**: Optuna-тюнингованные (50 trials, см. [`artifacts/reports/optuna_best_params.json`](../artifacts/reports/optuna_best_params.json))
**Постпроцессинг**: Holiday safety margin ×1.05 на часы внутри российского праздничного блока

Все три компонента работают вместе — выключение любого ломает контракт «Coverage ≥ 90% на праздниках».

## Ключевые файлы

| Файл | Что делает |
|------|-----------|
| [`src/crocs/ml/lightgbm_model.py`](../src/crocs/ml/lightgbm_model.py) | `TUNED_LGBM_PARAMS` + `train_lightgbm()` + `FEATURE_COLUMNS` (28 фич) |
| [`src/crocs/ml/ensemble_model.py`](../src/crocs/ml/ensemble_model.py) | Упрощён до single LGBM (BASE_MODEL_NAMES = ("lightgbm",)) |
| [`src/crocs/ml/lightgbm_pipeline.py`](../src/crocs/ml/lightgbm_pipeline.py) | `HOLIDAY_SAFETY_MARGIN`, `apply_holiday_safety_margin()`, `run_ensemble_forecast()` |
| [`scripts/run_lightgbm_forecast.py`](../scripts/run_lightgbm_forecast.py) | CLI: `--holiday-margin 1.05` (default), `--start`, `--end` |
| [`scripts/train_and_save_model.py`](../scripts/train_and_save_model.py) | Обучить и сохранить модель в `models/` (для дебага/быстрого инференса) |
| [`models/lightgbm_production.txt`](../models/lightgbm_production.txt) | Снэпшот обученной модели |
| [`models/lightgbm_production_meta.json`](../models/lightgbm_production_meta.json) | Метаданные: параметры, CV-метрики, дата обучения |

## Зачем такие решения

### Почему single LightGBM, а не ансамбль?

Bake-off на 6 фолдах CV ([notebook §4](../notebooks/02_model_selection_journey.ipynb)) показал:
- Ансамбль (RF + XGB + CatBoost + LGBM) лучше single LGBM на **0.5 п.п. WAPE**
- Цена: 4× время обучения, 4× размер модели, 4× места в проде
- Не оправдано

### Почему quantile@0.7, а не MSE?

Бизнес-приоритет: «пусть лучше больше людей работают» (недокомплект дороже перекомплекта).
- MSE даёт **симметричную** ошибку → центр распределения → Coverage 72.6% на праздниках
- `quantile @ 0.7` даёт **70-й перцентиль** → страховка вверх → Coverage 84.8% на праздниках
- + margin 1.05 → Coverage **90.2%** ✅ цель

### Почему margin = 1.05?

Калибровка на CV ([artifacts/reports/final_model_comparison.csv](../artifacts/reports/final_model_comparison.csv)):

| Margin | Holiday Coverage | Holiday WAPE |
|--------|------------------|--------------|
| 1.00 | 84.8% | 14.1% |
| **1.05** | **90.2%** ✅ | 16.1% |
| 1.10 | 94.6% | 19.7% |
| 1.20 | 97.9% | 28.7% |

1.05 — минимум для Coverage ≥ 90%. Поднимать выше — overstaffing растёт быстрее точности.

## Целевые метрики (CV на 6 фолдах)

| Метрика | Цель | Достигнуто |
|---------|------|-----------|
| Coverage на праздниках | ≥ 90% | **90.2%** ✅ |
| Coverage на обычных днях | ≥ 95% | **96.7%** ✅ |
| Understaffing на праздниках | минимизировать | **0.16 сотр/час** (в 2.75× меньше M2) |
| WAPE на обычных | < 9% | 11.9% ❌ |
| WAPE на праздниках | < 12% | 16.1% ❌ |

**WAPE выше целей — ожидаемая плата за асимметрию.** Сделка: +4 п.п. WAPE за +18 п.п. Coverage.

## Запуск прогноза

```bash
# Стандартный прогноз на майские
uv run python scripts/run_lightgbm_forecast.py \
    --data-dir data/raw \
    --output-dir data/output \
    --start 2026-04-27 \
    --end 2026-05-03

# Отключить margin (для сравнения)
uv run python scripts/run_lightgbm_forecast.py ... --holiday-margin 1.0

# Усилить страховку
uv run python scripts/run_lightgbm_forecast.py ... --holiday-margin 1.10
```

Каждый запуск:
1. Обучает модель с нуля на самых свежих данных
2. Делает CV (rolling + seasonal) и пишет метрики
3. Прогнозирует на заданный период
4. Сохраняет результат в `data/output/lightgbm_forecast{N}.xlsx`

## Тесты

```bash
uv run pytest tests/test_smoke.py -v
```

13 тестов — версия, фичи, голидеи, погода, supervised frame, single LGBM в проде, margin постпроцессинг.

## Что НЕ сделано (можно дотюнить)

1. **Holiday-aware lags** (`lag_363`, `lag_365`, `lag_366`) — компенсация високосного года. Ожидаемый эффект: −1-2 п.п. WAPE на праздниках. ~1 час работы.
2. **Margin по типам праздников** — 1 мая ≠ 9 мая ≠ 23 фев требуют разных коэффициентов. Coverage до 95% без роста WAPE. ~4 часа.
3. **Holiday-specific booster** — отдельная модель только на праздничных днях. −2-3 п.п. WAPE на праздниках. ~1 день.
4. **Restoring ensemble под quantile** — RF не умеет quantile, остальные 3 модели могут. −0.5 п.п. WAPE. ~1 день.

## История решений

Подробный разбор в [`notebooks/02_model_selection_journey.ipynb`](../notebooks/02_model_selection_journey.ipynb):
- §2 — почему убрали 12 weather + 5 salary + 8 cyclic фич
- §3 — почему WAPE а не MAPE, бизнес-метрики через `reqlabor`
- §4 — bake-off 5 архитектур × 6 фолдов
- §5 — выбор single LGBM поверх ансамбля
- §6 — Optuna search space
- §7 — финальные результаты + калибровка margin

## Артефакты

- [`artifacts/reports/optuna_best_params.json`](../artifacts/reports/optuna_best_params.json) — гиперпараметры
- [`artifacts/reports/final_model_comparison.csv`](../artifacts/reports/final_model_comparison.csv) — CV-результаты всех подходов
- [`artifacts/reports/cv_bakeoff.csv`](../artifacts/reports/cv_bakeoff.csv) — детали bake-off по 6 фолдам
- [`artifacts/reports/current_lightgbm_feature_importance.csv`](../artifacts/reports/current_lightgbm_feature_importance.csv) — важность фич
- [`artifacts/figures/final_model_comparison.png`](../artifacts/figures/final_model_comparison.png) — главный график
- [`artifacts/figures/cv_bakeoff_comparison.png`](../artifacts/figures/cv_bakeoff_comparison.png) — детальный bake-off
