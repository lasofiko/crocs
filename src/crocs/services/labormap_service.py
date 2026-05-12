from __future__ import annotations

import re

import pandas as pd


def _norm_ver(s: object) -> str:
    t = str(s).strip()
    t = t.replace("\u2019", "'").replace("’", "'")
    return re.sub(r"\s+", " ", t)


def _version_label(ts: pd.Timestamp, hour: int) -> str:
    dow = ts.dayofweek
    weekend = dow >= 5
    menu = "утр." if hour < 10 else "осн."
    prefix = "вых" if weekend else "будни"
    return f"{prefix}/{menu}"


def _rows_for_version(rl: pd.DataFrame, station: str, ver: str) -> pd.DataFrame:
    st = str(station)
    v = _norm_ver(ver)
    sub = rl[rl["station_key"].astype(str) == st]
    if sub.empty:
        return sub
    ex = sub[sub["version"].map(_norm_ver) == v]
    if not ex.empty:
        return ex
    ex2 = sub[sub["version"].map(_norm_ver).str.replace(".", "", regex=False) == v.replace(".", "")]
    if not ex2.empty:
        return ex2
    return sub[sub["version"].map(_norm_ver).str.contains(v.split("/")[0], regex=False)]


def _required_tier(sub: pd.DataFrame, guests: float) -> int:
    if sub.empty:
        return 0
    s = sub.sort_values("guests_count")
    for _, r in s.iterrows():
        if float(guests) <= float(r["guests_count"]):
            return int(r["reqlabor"])
    return int(s.iloc[-1]["reqlabor"])


def build_hourly_demand(forecast_guests: pd.DataFrame, reqlabor: pd.DataFrame) -> pd.DataFrame:

    if reqlabor.empty:
        return pd.DataFrame(
            columns=["ds", "sale_hour", "station_key", "required_employees", "assigned_employees"],
        )

    rl = reqlabor.copy()
    rl.columns = [str(c).strip().lower() for c in rl.columns]
    for col in ("station_key", "version", "guests_count", "reqlabor"):
        if col not in rl.columns:
            raise ValueError(f"reqlabor: нет колонки {col}")
    rl["version"] = rl["version"].map(_norm_ver)

    stations = sorted(rl["station_key"].dropna().astype(str).unique().tolist())
    f = forecast_guests.copy()
    f.columns = [str(c).strip().lower() for c in f.columns]

    out: list[dict] = []
    for _, row in f.iterrows():
        ds = pd.to_datetime(row["sale_date"], errors="coerce")
        if pd.isna(ds):
            continue
        hour = int(row["sale_hour"])
        guests = float(row["guests_count"])
        ver = _version_label(ds, hour)
        for st in stations:
            part = _rows_for_version(rl, st, ver)
            need = _required_tier(part, guests)
            out.append(
                {
                    "ds": ds.normalize(),
                    "sale_hour": hour,
                    "station_key": st,
                    "required_employees": need,
                }
            )
    return pd.DataFrame(out)


def effective_station_floor(floor_n: int, sale_hour: int, relaxed_sale_hours: frozenset[int]) -> int:
    """Минимальное число людей на станции в слоте sale_hour с учётом relaxed-часов."""
    if floor_n <= 0:
        return 0
    if int(sale_hour) in relaxed_sale_hours:
        return 1
    return floor_n


def apply_min_employees_per_station(
    demand: pd.DataFrame,
    floor_n: int,
    *,
    relaxed_sale_hours: frozenset[int] | None = None,
) -> pd.DataFrame:
    """Поднимает required_employees до эффективного минимума в каждой строке (день, час, станция)."""
    if floor_n <= 0 or demand.empty:
        return demand
    relax = relaxed_sale_hours or frozenset()
    out = demand.copy()
    cols = {str(c).strip().lower(): c for c in out.columns}
    req_col = cols.get("required_employees")
    if req_col is None:
        return out
    nums = pd.to_numeric(out[req_col], errors="coerce").fillna(0)
    hour_col = cols.get("sale_hour")
    if relax and hour_col is not None:
        h = pd.to_numeric(out[hour_col], errors="coerce")
        lower = h.map(
            lambda x: float(effective_station_floor(floor_n, int(x), relax))
            if pd.notna(x)
            else float(floor_n),
        )
        out[req_col] = nums.clip(lower=lower).round().astype(int)
    else:
        out[req_col] = nums.clip(lower=float(floor_n)).round().astype(int)
    return out
