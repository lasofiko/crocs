from __future__ import annotations

import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from crocs.services.staffing_counts import staff_counts_per_slot

# Меньше файлов и быстрее сохранение, чем dpi=150 при сопоставимой читаемости.
_FIGURE_DPI = 120


def _forecast_datetime(frame: pd.DataFrame) -> pd.Series:
    f = frame.copy()
    f.columns = [str(c).strip().lower() for c in f.columns]
    dt = pd.to_datetime(f["sale_date"])
    return dt + pd.to_timedelta(f["sale_hour"].astype(int), unit="h")


def plot_forecast_guests(forecast_df: pd.DataFrame, path: Path) -> None:
    """График 1: почасовой прогноз гостей на горизонте."""
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
    fig.savefig(path, dpi=_FIGURE_DPI)
    plt.close(fig)


def _plot_gantt_on_ax(
    ax: plt.Axes,
    schedule_df: pd.DataFrame,
    day_ts: pd.Timestamp,
    station: str,
    open_h: int,
    close_h: int,
) -> None:
    s = schedule_df
    part = s[(s["ds"] == day_ts) & (s["station_key"].astype(str) == str(station))].copy()
    if part.empty:
        ax.set_axis_off()
        ax.set_title(f"{station}\n(нет смен)", fontsize=9)
        return
    part = part.sort_values("employee_id")
    y_labels = [str(x) for x in part["employee_id"].tolist()]
    y_pos = range(len(part))
    for y, (_, row) in zip(y_pos, part.iterrows()):
        t0 = float(row["starttime"])
        t1 = float(row["finishtime"])
        ax.barh(
            y,
            left=t0,
            width=max(0, t1 - t0),
            height=0.6,
            color="#1d4ed8",
            edgecolor="white",
        )
    ax.set_yticks(list(y_pos))
    ax.set_yticklabels(y_labels, fontsize=7)
    ax.set_xlabel("Час", fontsize=8)
    ax.set_xlim(open_h, close_h + 1)
    ax.set_title(str(station), fontsize=9)
    ax.grid(True, axis="x", alpha=0.3)


def _plot_coverage_on_ax(
    ax: plt.Axes,
    demand_day_station: pd.DataFrame,
    assigned_day_station: pd.DataFrame,
    day_ts: pd.Timestamp,
    station: str,
    open_h: int,
    close_h: int,
    *,
    legend_labels: bool,
) -> None:
    hours = list(range(open_h, close_h))
    req_map = {
        int(r["sale_hour"]): float(r["required_employees"])
        for _, r in demand_day_station.iterrows()
    }
    as_map = {int(r["sale_hour"]): int(r["assigned"]) for _, r in assigned_day_station.iterrows()}
    req = [req_map.get(h, 0.0) for h in hours]
    asn = [float(as_map.get(h, 0)) for h in hours]

    ax.plot(
        hours,
        req,
        "o-",
        color="#dc2626",
        markersize=3,
        linewidth=1,
        label="Нужно" if legend_labels else None,
    )
    ax.plot(
        hours,
        asn,
        "s-",
        color="#16a34a",
        markersize=3,
        linewidth=1,
        label="Назначено" if legend_labels else None,
    )
    ax.set_xlabel("Час", fontsize=8)
    ax.set_ylabel("Чел.", fontsize=8)
    ax.set_title(str(station), fontsize=9)
    ax.set_xticks(hours[:: max(1, len(hours) // 8)])
    if legend_labels:
        ax.legend(fontsize=7, loc="upper right")
    ax.grid(True, alpha=0.3)


def plot_gantt_day_all_stations(
    schedule_prepared: pd.DataFrame,
    day,
    stations: list[str],
    path: Path,
    open_h: int,
    close_h: int,
) -> None:
    """Один PNG на день: сетка Gantt по станциям.

    ``schedule_prepared`` — lower-case колонки, ``ds`` нормализован.
    """
    if not stations:
        return
    s = schedule_prepared
    day_ts = pd.Timestamp(day).normalize()

    n = len(stations)
    ncols = min(3, n)
    nrows = int(math.ceil(n / ncols))
    fig_w = 4.2 * ncols
    fig_h = max(2.6, 2.4 * nrows)
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), squeeze=False)
    fig.suptitle(f"Расписание (Gantt): {day_ts.date()}", fontsize=11, y=1.02)

    for idx, st in enumerate(stations):
        r, c = divmod(idx, ncols)
        _plot_gantt_on_ax(axes[r][c], s, day_ts, st, open_h, close_h)

    for j in range(n, nrows * ncols):
        r, c = divmod(j, ncols)
        axes[r][c].set_axis_off()

    fig.tight_layout()
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def plot_coverage_day_all_stations(
    demand_prepared: pd.DataFrame,
    assigned_df: pd.DataFrame,
    day,
    stations: list[str],
    path: Path,
    open_h: int,
    close_h: int,
) -> None:
    """Один PNG на день: покрытие по станциям (нужно vs назначено).

    ``demand_prepared`` — уже lower-case колонки и ``ds`` нормализованы к дате.
    """
    if not stations:
        return
    d = demand_prepared
    day_ts = pd.Timestamp(day).normalize()

    ad = assigned_df
    if not ad.empty:
        ad = ad.copy()
        ad["ds"] = pd.to_datetime(ad["ds"], errors="coerce").dt.normalize()

    n = len(stations)
    ncols = min(3, n)
    nrows = int(math.ceil(n / ncols))
    fig_w = 4.2 * ncols
    fig_h = max(2.6, 2.4 * nrows)
    fig, axes = plt.subplots(nrows, ncols, figsize=(fig_w, fig_h), squeeze=False)
    fig.suptitle(f"Покрытие спроса: {day_ts.date()}", fontsize=11, y=1.02)

    for idx, st in enumerate(stations):
        r, c = divmod(idx, ncols)
        sub = d[(d["ds"] == day_ts) & (d["station_key"].astype(str) == str(st))].copy()
        if ad.empty:
            asub = pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])
        else:
            asub = ad[(ad["ds"] == day_ts) & (ad["station_key"].astype(str) == str(st))].copy()
        _plot_coverage_on_ax(
            axes[r][c],
            sub,
            asub,
            day_ts,
            st,
            open_h,
            close_h,
            legend_labels=(idx == 0),
        )

    for j in range(n, nrows * ncols):
        r, c = divmod(j, ncols)
        axes[r][c].set_axis_off()

    fig.tight_layout()
    fig.savefig(path, dpi=_FIGURE_DPI, bbox_inches="tight")
    plt.close(fig)


def write_pipeline_figures(
    forecast_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    demand_df: pd.DataFrame,
    figures_root: Path,
    *,
    open_hour: int,
    close_hour: int,
) -> None:
    """
    Пишет графики в ``figures_root``:

    - ``01_forecast_guests.png`` — прогноз гостей;
    - ``02_schedule_gantt/YYYY-MM-DD.png`` — по **одному** файлу на день, все станции сеткой;
    - ``03_staffing_coverage/YYYY-MM-DD.png`` — то же для «нужно vs назначено».

    ``staff_counts_per_slot`` считается один раз на весь горизонт (ускорение).
    """
    figures_root.mkdir(parents=True, exist_ok=True)
    plot_forecast_guests(forecast_df, figures_root / "01_forecast_guests.png")

    gantt_dir = figures_root / "02_schedule_gantt"
    gantt_dir.mkdir(parents=True, exist_ok=True)
    cov_dir = figures_root / "03_staffing_coverage"
    cov_dir.mkdir(parents=True, exist_ok=True)

    dem = demand_df.copy()
    dem.columns = [str(c).strip().lower() for c in dem.columns]
    dem["ds"] = pd.to_datetime(dem["ds"], errors="coerce").dt.normalize()

    sch = schedule_df
    if sch is not None and not sch.empty:
        sch = sch.copy()
        sch.columns = [str(c).strip().lower() for c in sch.columns]
        sch["ds"] = pd.to_datetime(sch["ds"], errors="coerce").dt.normalize()
    else:
        sch = pd.DataFrame(columns=["ds", "station_key", "employee_id", "starttime", "finishtime"])

    assigned_df = staff_counts_per_slot(
        schedule_df if schedule_df is not None and not schedule_df.empty else pd.DataFrame(),
        open_hour,
        close_hour,
    )

    pairs_dem = dem[["ds", "station_key"]].drop_duplicates()
    pairs_sch = (
        sch[["ds", "station_key"]].drop_duplicates()
        if not sch.empty
        else pd.DataFrame(columns=["ds", "station_key"])
    )
    pairs = pd.concat([pairs_dem, pairs_sch], ignore_index=True).drop_duplicates()

    if pairs.empty:
        return

    days = sorted(pd.to_datetime(pairs["ds"]).dt.normalize().unique())
    for day_ts in days:
        day_stations = (
            pairs[pairs["ds"] == day_ts]["station_key"]
            .astype(str)
            .drop_duplicates()
            .sort_values()
            .tolist()
        )
        if not day_stations:
            continue
        stem = pd.Timestamp(day_ts).strftime("%Y-%m-%d")
        plot_gantt_day_all_stations(
            sch,
            day_ts,
            day_stations,
            gantt_dir / f"{stem}.png",
            open_hour,
            close_hour,
        )
        plot_coverage_day_all_stations(
            dem,
            assigned_df,
            day_ts,
            day_stations,
            cov_dir / f"{stem}.png",
            open_hour,
            close_hour,
        )
