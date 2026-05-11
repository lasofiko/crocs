from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

_FIGURE_DPI = 120


def _forecast_datetime(frame: pd.DataFrame) -> pd.Series:
    f = frame.copy()
    f.columns = [str(c).strip().lower() for c in f.columns]
    dt = pd.to_datetime(f["sale_date"])
    return dt + pd.to_timedelta(f["sale_hour"].astype(int), unit="h")


def plot_forecast_guests(forecast_df: pd.DataFrame, path: Path) -> None:
    """Почасовой прогноз гостей на горизонте."""
    f = forecast_df.copy()
    f.columns = [str(c).strip().lower() for c in f.columns]
    ts = _forecast_datetime(f)
    order = ts.argsort()
    fig, ax = plt.subplots(figsize=(14, 5))
    ax.plot(ts.iloc[order], f["guests_count"].astype(float).iloc[order], color="#2563eb", linewidth=1.2)
    ax.fill_between(
        ts.iloc[order],
        f["guests_count"].astype(float).iloc[order],
        alpha=0.15,
        color="#2563eb",
    )
    ax.set_xlabel("Дата и час")
    ax.set_ylabel("Гости (прогноз)")
    ax.set_title("Почасовой прогноз числа гостей")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=_FIGURE_DPI)
    plt.close(fig)
