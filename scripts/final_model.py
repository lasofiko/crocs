# ruff: noqa: E402,E501

from __future__ import annotations

import io
import sys

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import warnings
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
plt.rcParams["font.family"] = "DejaVu Sans"

try:
    import shap
    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False

from crocs.ml.baseline import build_future_calendar
from crocs.ml.features import MODEL_TRAIN_START
from crocs.ml.production import (
    CATS,
    HOURS_DEFAULT,
    TABULAR,
    build_frame,
    interpolate_weather,
    make_sample_weights,
    predict_recursive,
    prep_for_cat,
    train_model,
    upcoming_break_days,
)

FORECAST_START = date(2026, 4, 27)
FORECAST_END = date(2026, 5, 3)
CV_FOLDS = [
    ("holiday_may2025", pd.Timestamp("2025-04-27"), pd.Timestamp("2025-05-03")),
    ("recent_w1",       pd.Timestamp("2026-04-20"), pd.Timestamp("2026-04-26")),
    ("recent_w2",       pd.Timestamp("2026-04-13"), pd.Timestamp("2026-04-19")),
    ("recent_w3",       pd.Timestamp("2026-04-06"), pd.Timestamp("2026-04-12")),
    ("recent_w4",       pd.Timestamp("2026-03-30"), pd.Timestamp("2026-04-05")),
]


def compute_metrics(actual: pd.DataFrame, predicted: pd.DataFrame) -> dict:
    actual = actual.copy()
    predicted = predicted.copy()
    actual["sale_date"] = pd.to_datetime(actual["sale_date"]).dt.normalize().dt.date
    predicted["sale_date"] = pd.to_datetime(predicted["sale_date"]).dt.normalize().dt.date
    m = actual.merge(predicted, on=["sale_date", "sale_hour"], suffixes=("_act", "_pred"))
    y = m["guests_count_act"].astype(float).to_numpy()
    yhat = m["guests_count_pred"].astype(float).to_numpy()
    diff = yhat - y
    return {
        "wape": float(np.sum(np.abs(diff)) / np.sum(np.abs(y))) if np.sum(np.abs(y)) > 0 else float("inf"),
        "mae":  float(np.mean(np.abs(diff))),
        "rmse": float(np.sqrt(np.mean(diff ** 2))),
        "bias": float(np.mean(diff)),
        "rows": len(m),
        "merged": m,
    }


def save_submission(forecast: pd.DataFrame, name: str = "final.csv") -> Path:
    sub = pd.DataFrame({
        "ID": pd.to_datetime(forecast["sale_date"]).dt.strftime("%Y-%m-%d") + "-" +
              forecast["sale_hour"].astype(str).str.zfill(2),
        "guests_count": forecast["guests_count"].astype(int),
    })
    out = Path(f"data/output/{name}")
    sub.to_csv(out, index=False)
    print(f"  -> {out}  ({sub['guests_count'].sum():,} guests)")
    return out


def sanity_check_calendar() -> None:
    print("\nSanity check break-day features:")
    print(f"  {'Date':12s}  {'DOW':4s}  {'expected':10s}  {'actual':10s}  OK?")
    cases = [
        (pd.Timestamp("2024-04-30"), "Tue", 1),
        (pd.Timestamp("2025-04-30"), "Wed", 4),
        (pd.Timestamp("2025-05-01"), "Thu", 3),
        (pd.Timestamp("2025-05-07"), "Wed", 4),
        (pd.Timestamp("2026-04-30"), "Thu", 3),
        (pd.Timestamp("2026-05-01"), "Fri", 2),
        (pd.Timestamp("2026-05-08"), "Fri", 3),
    ]
    for d, dow, expected in cases:
        actual = upcoming_break_days(d)
        ok = "OK" if actual == expected else "FAIL"
        print(f"  {d.date()!s:12s}  {dow:4s}  {expected:10d}  {actual:10d}  {ok}")


def main() -> None:
    print("Loading data...")
    train = pd.read_csv("data/raw/train.csv")
    train["sale_date"] = pd.to_datetime(train["sale_date"])
    train = train[train["sale_date"] >= MODEL_TRAIN_START].copy()
    print(f"  Train: {len(train):,} rows, {train['sale_date'].min().date()} -> {train['sale_date'].max().date()}")

    weather_raw = pd.read_csv("data/raw/weather_moscow.csv")
    weather_raw["sale_date"] = pd.to_datetime(weather_raw["sale_date"])
    weather_interp = interpolate_weather(weather_raw)
    print(f"  Weather: {len(weather_raw):,} obs -> {len(weather_interp):,} interpolated")

    sanity_check_calendar()

    print(f"\nWalk-forward CV ({len(CV_FOLDS)} folds)")
    print(f"  {'Fold':25s}  {'Period':30s}  {'WAPE':>7s}  {'MAE':>7s}  {'Bias':>7s}")
    cv_results = []
    fold_predictions = {}

    for fold_name, val_start, val_end in CV_FOLDS:
        train_fold = train[train["sale_date"] < val_start].copy()
        actual_fold = train[(train["sale_date"] >= val_start) & (train["sale_date"] <= val_end)].copy()
        if len(actual_fold) == 0:
            continue

        cal_fold = actual_fold[["sale_date", "sale_hour"]].copy()
        frame_fold = build_frame(train_fold, weather_interp)
        weights_fold = make_sample_weights(frame_fold)
        model_fold = train_model(frame_fold, weights_fold)
        pred_fold = predict_recursive(model_fold, train_fold, cal_fold, weather_interp)

        metrics = compute_metrics(actual_fold, pred_fold)
        cv_results.append({
            "fold": fold_name, "val_start": val_start.date(), "val_end": val_end.date(),
            **{k: v for k, v in metrics.items() if k != "merged"},
        })
        fold_predictions[fold_name] = (actual_fold, pred_fold)
        period = f"{val_start.date()} -> {val_end.date()}"
        print(f"  {fold_name:25s}  {period:30s}  {metrics['wape']:7.4f}  {metrics['mae']:7.2f}  {metrics['bias']:+7.2f}")

    cv_df = pd.DataFrame(cv_results)
    cv_df.to_csv("artifacts/reports/final_cv.csv", index=False)
    print(f"\n  CV mean WAPE:  {cv_df['wape'].mean():.4f}")
    print(f"  Holiday WAPE:  {cv_df.loc[cv_df['fold'] == 'holiday_may2025', 'wape'].iloc[0]:.4f}")

    print(f"\nFinal training on full data (through {train['sale_date'].max().date()})")
    frame_full = build_frame(train, weather_interp)
    weights_full = make_sample_weights(frame_full)
    print(f"  Train frame: {len(frame_full):,} rows x {len(TABULAR)} features ({len(CATS)} categorical)")
    model_full = train_model(frame_full, weights_full)

    print(f"\nForecast {FORECAST_START} -> {FORECAST_END}")
    cal_fc = build_future_calendar(FORECAST_START, FORECAST_END, hours=HOURS_DEFAULT)
    forecast = predict_recursive(model_full, train, cal_fc, weather_interp)
    save_submission(forecast, "final.csv")

    forecast_xlsx = forecast.copy()
    forecast_xlsx["sale_date"] = pd.to_datetime(forecast_xlsx["sale_date"]).dt.date
    xlsx_path = Path("data/output/forecast.xlsx")
    forecast_xlsx[["sale_date", "sale_hour", "guests_count"]].to_excel(xlsx_path, index=False)
    print(f"  -> {xlsx_path}")

    Path("artifacts/figures").mkdir(parents=True, exist_ok=True)

    importance = pd.DataFrame({
        "feature": TABULAR,
        "importance": model_full.get_feature_importance(),
    }).sort_values("importance", ascending=False)
    importance.to_csv("artifacts/reports/feature_importance.csv", index=False)
    print("\n  Top-10 features:")
    for _, row in importance.head(10).iterrows():
        print(f"    {row['feature']:32s}  {row['importance']:6.2f}")

    if HAS_SHAP:
        try:
            sample = frame_full.sample(min(500, len(frame_full)), random_state=42)
            feat = prep_for_cat(sample)
            from catboost import Pool
            cat_idx = [TABULAR.index(c) for c in CATS]
            pool = Pool(feat, cat_features=cat_idx)
            shap_values = model_full.get_feature_importance(pool, type="ShapValues")[:, :-1]
            plt.figure(figsize=(10, 8))
            shap.summary_plot(shap_values, feat, feature_names=TABULAR, show=False, max_display=20)
            plt.tight_layout()
            plt.savefig("artifacts/figures/shap_final.png", dpi=120, bbox_inches="tight")
            plt.close()
        except Exception as e:
            print(f"  SHAP failed: {e}")

    for fold_name, (actual, pred) in fold_predictions.items():
        actual = actual.copy()
        pred = pred.copy()
        actual["sale_date"] = pd.to_datetime(actual["sale_date"]).dt.normalize().dt.date
        pred["sale_date"] = pd.to_datetime(pred["sale_date"]).dt.normalize().dt.date
        m = actual.merge(pred, on=["sale_date", "sale_hour"], suffixes=("_act", "_pred"))
        m["residual"] = m["guests_count_act"] - m["guests_count_pred"]
        m["fold"] = fold_name
        m.to_csv(f"artifacts/reports/final_residuals_{fold_name}.csv", index=False)

    print("\nDone")
    print("  Submission:   data/output/final.csv")
    print("  Backend xlsx: data/output/forecast.xlsx")
    print(f"  Holiday WAPE: {cv_df.loc[cv_df['fold'] == 'holiday_may2025', 'wape'].iloc[0]:.4f}")


if __name__ == "__main__":
    main()
