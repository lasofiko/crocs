from __future__ import annotations

import re

import pandas as pd


def _norm_ver(s: object) -> str:
    t = str(s).strip()
    t = t.replace("\u2019", "'").replace("’", "'")
    return re.sub(r"\s+", " ", t)


def _version_label(ts: pd.Timestamp, hour: int) -> str:
    """Совпадает с описанием кейса: будни/вых × утр./осн., утро до 10:00."""
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
    """
    Заглушка: guests_count -> reqlabor по правилам version и ступеням guests_count.
    Потом уточнить строгое сопоставление version и границ гостей.
    """
    if reqlabor.empty:
        return pd.DataFrame(columns=["ds", "sale_hour", "station_key", "required_employees"])

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
