from __future__ import annotations

import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def _slug(text: str) -> str:
    t = re.sub(r'[/\\:*?"<>|]', "_", str(text).strip())
    return t[:120] if len(t) > 120 else t


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
    fig.savefig(path, dpi=150)
    plt.close(fig)


def _shift_covers_hour(start: float, finish: float, hour: int) -> bool:
    return start <= hour < finish


def staff_counts_per_slot(schedule_df: pd.DataFrame, open_h: int, close_h: int) -> pd.DataFrame:
    """Число назначенных сотрудников по (ds, sale_hour, station_key)."""
    if schedule_df is None or schedule_df.empty:
        return pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])

    s = schedule_df.copy()
    s.columns = [str(c).strip().lower() for c in s.columns]
    s["ds"] = pd.to_datetime(s["ds"], errors="coerce").dt.normalize()
    rows: list[dict] = []
    for _, r in s.iterrows():
        if pd.isna(r["ds"]):
            continue
        st = str(r["station_key"])
        t0 = float(r["starttime"])
        t1 = float(r["finishtime"])
        for h in range(open_h, close_h):
            if _shift_covers_hour(t0, t1, h):
                rows.append({"ds": r["ds"], "sale_hour": h, "station_key": st})
    if not rows:
        return pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])
    return (
        pd.DataFrame(rows)
        .groupby(["ds", "sale_hour", "station_key"])
        .size()
        .reset_index(name="assigned")
    )


def plot_gantt_day_station(
    schedule_df: pd.DataFrame,
    day,
    station: str,
    path: Path,
    open_h: int,
    close_h: int,
) -> None:
    """График 2: Gantt смены сотрудников на станции в выбранный день."""
    s = schedule_df.copy()
    s.columns = [str(c).strip().lower() for c in s.columns]
    s["ds"] = pd.to_datetime(s["ds"], errors="coerce").dt.normalize()
    day_ts = pd.Timestamp(day).normalize()
    part = s[(s["ds"] == day_ts) & (s["station_key"].astype(str) == str(station))].copy()
    if part.empty:
        return

    part = part.sort_values("employee_id")
    y_labels = [str(x) for x in part["employee_id"].tolist()]
    y_pos = range(len(part))
    fig, ax = plt.subplots(figsize=(12, max(3, 0.4 * len(part))))
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
    ax.set_yticklabels(y_labels)
    ax.set_xlabel("Час")
    ax.set_xlim(open_h, close_h + 1)
    ax.set_title(f"Расписание: {day_ts.date()} — станция {station}")
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_coverage_day_station(
    demand_df: pd.DataFrame,
    schedule_df: pd.DataFrame,
    day,
    station: str,
    path: Path,
    open_h: int,
    close_h: int,
) -> None:
    """График 3: потребность vs назначено по часам."""
    d = demand_df.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]
    d["ds"] = pd.to_datetime(d["ds"], errors="coerce").dt.normalize()
    day_ts = pd.Timestamp(day).normalize()
    sub = d[(d["ds"] == day_ts) & (d["station_key"].astype(str) == str(station))].copy()
    assigned_df = staff_counts_per_slot(schedule_df, open_h, close_h)
    if not assigned_df.empty:
        assigned_df["ds"] = pd.to_datetime(assigned_df["ds"], errors="coerce").dt.normalize()
        asub = assigned_df[
            (assigned_df["ds"] == day_ts) & (assigned_df["station_key"].astype(str) == str(station))
        ]
    else:
        asub = pd.DataFrame(columns=["ds", "sale_hour", "station_key", "assigned"])

    hours = list(range(open_h, close_h))
    req_map = {int(r["sale_hour"]): float(r["required_employees"]) for _, r in sub.iterrows()}
    as_map = {int(r["sale_hour"]): int(r["assigned"]) for _, r in asub.iterrows()}
    req = [req_map.get(h, 0.0) for h in hours]
    asn = [float(as_map.get(h, 0)) for h in hours]

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(hours, req, "o-", color="#dc2626", label="Нужно (по нормативу)")
    ax.plot(hours, asn, "s-", color="#16a34a", label="Назначено (по сменам)")
    ax.set_xlabel("Час")
    ax.set_ylabel("Человек")
    ax.set_title(f"Покрытие спроса: {day_ts.date()} — {station}")
    ax.set_xticks(hours)
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
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
    - ``02_schedule_gantt/*.png`` — Gantt по каждой паре день×станция (если есть смены);
    - ``03_staffing_coverage/*.png`` — нужно vs назначено по каждой паре день×станция.
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
    pairs_dem = dem[["ds", "station_key"]].drop_duplicates()

    pairs_sch = pd.DataFrame(columns=["ds", "station_key"])
    if schedule_df is not None and not schedule_df.empty:
        sch = schedule_df.copy()
        sch.columns = [str(c).strip().lower() for c in sch.columns]
        sch["ds"] = pd.to_datetime(sch["ds"], errors="coerce").dt.normalize()
        pairs_sch = sch[["ds", "station_key"]].drop_duplicates()

    pairs = pd.concat([pairs_dem, pairs_sch], ignore_index=True).drop_duplicates()

    for _, row in pairs.iterrows():
        ds = row["ds"]
        st = str(row["station_key"])
        stem = f"{pd.Timestamp(ds).strftime('%Y-%m-%d')}_{_slug(st)}"
        plot_coverage_day_station(
            demand_df,
            schedule_df if schedule_df is not None else pd.DataFrame(),
            ds,
            st,
            cov_dir / f"{stem}.png",
            open_hour,
            close_hour,
        )
        plot_gantt_day_station(
            schedule_df if schedule_df is not None else pd.DataFrame(),
            ds,
            st,
            gantt_dir / f"{stem}.png",
            open_hour,
            close_hour,
        )
