"""SQLite: сохранение и восстановление прогонов расписания (CP-SAT + LNS)."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, NamedTuple

import pandas as pd


class ScheduleCacheHit(NamedTuple):
    """Результат чтения кэша: exact — полный cache_key; inputs_fingerprint — те же входы, другой сценарий солвера."""

    schedule_df: pd.DataFrame
    labor_df: pd.DataFrame
    run_id: int
    match_kind: Literal["exact", "inputs_fingerprint"]


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _table_blob_digest(df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        return "empty"
    cols = sorted(str(c) for c in df.columns)
    norm = df[cols].sort_values(cols).reset_index(drop=True)
    return hashlib.sha256(norm.to_csv(index=False).encode("utf-8", errors="replace")).hexdigest()[:24]


def _bundle_fingerprint(bundle: "RawDataBundle") -> str:
    return "|".join(
        [
            _table_blob_digest(bundle.reqlabor),
            _table_blob_digest(bundle.sched),
            _table_blob_digest(bundle.staff_limits),
            _table_blob_digest(bundle.station_priorities),
            _table_blob_digest(bundle.shifts),
        ]
    )


def _demand_digest(demand_df: pd.DataFrame) -> str:
    dcols = sorted(demand_df.columns, key=str)
    dnorm = demand_df[dcols].sort_values(list(demand_df.columns)).reset_index(drop=True)
    return hashlib.sha256(
        dnorm.to_csv(index=False).encode("utf-8", errors="replace"),
    ).hexdigest()[:24]


def compute_schedule_inputs_fingerprint(
    *,
    forecast_digest: str,
    demand_df: pd.DataFrame,
    bundle: "RawDataBundle",
    sch: "SchedulingConfig",
    restaurant_open_hour: int,
    restaurant_close_hour: int,
) -> str:
    """
    Отпечаток входов постановки задачи без «сценария» солвера (лимиты времени, LNS, seed и т.д.).

    Одинаковый fingerprint при разных solver_time_limit / LNS / first_solution_stop позволяет
    переиспользовать уже сохранённое расписание из SQLite.
    """
    bundle_fp = _bundle_fingerprint(bundle)
    demand_h = _demand_digest(demand_df)
    sch_struct: dict[str, Any] = {
        "max_extra_coverage": sch.max_extra_coverage,
        "min_employees_per_station": sch.min_employees_per_station,
        "min_employees_relaxed_sale_hours": list(sch.min_employees_relaxed_sale_hours),
        "max_shifts_per_employee_week": sch.max_shifts_per_employee_week,
        "require_one_shift_per_sched_employee": sch.require_one_shift_per_sched_employee,
    }
    sch_s = hashlib.sha256(json.dumps(sch_struct, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    raw = (
        f"v1inputs|{forecast_digest}|{bundle_fp}|{demand_h}|{sch_s}|"
        f"{restaurant_open_hour}|{restaurant_close_hour}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:48]


def compute_schedule_cache_key(
    *,
    forecast_digest: str,
    demand_df: pd.DataFrame,
    bundle: "RawDataBundle",
    sch: "SchedulingConfig",
    restaurant_open_hour: int,
    restaurant_close_hour: int,
) -> str:
    """Полный ключ: как inputs_fingerprint плюс параметры солвера и LNS (точное совпадение прогона)."""
    bundle_fp = _bundle_fingerprint(bundle)
    demand_h = _demand_digest(demand_df)
    sch_d: dict[str, Any] = {
        "solver_time_limit_seconds": sch.solver_time_limit_seconds,
        "cp_sat_stop_after_first_solution": sch.cp_sat_stop_after_first_solution,
        "max_extra_coverage": sch.max_extra_coverage,
        "min_employees_per_station": sch.min_employees_per_station,
        "min_employees_relaxed_sale_hours": list(sch.min_employees_relaxed_sale_hours),
        "max_shifts_per_employee_week": sch.max_shifts_per_employee_week,
        "require_one_shift_per_sched_employee": sch.require_one_shift_per_sched_employee,
        "lns_enabled": sch.lns_enabled,
        "lns_iterations": sch.lns_iterations,
        "lns_repair_seconds": sch.lns_repair_seconds,
        "lns_destroy_days_min": sch.lns_destroy_days_min,
        "lns_destroy_days_max": sch.lns_destroy_days_max,
        "lns_staff_destroy_fraction": sch.lns_staff_destroy_fraction,
        "lns_seed": sch.lns_seed,
    }
    sch_h = hashlib.sha256(json.dumps(sch_d, sort_keys=True).encode("utf-8")).hexdigest()[:20]
    raw = (
        f"v2|{forecast_digest}|{bundle_fp}|{demand_h}|{sch_h}|"
        f"{restaurant_open_hour}|{restaurant_close_hour}"
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:48]


def _ensure_cache_key_column(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(schedule_runs)").fetchall()
    names = {str(r[1]) for r in rows}
    if "cache_key" not in names:
        conn.execute("ALTER TABLE schedule_runs ADD COLUMN cache_key TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_schedule_runs_cache_key ON schedule_runs(cache_key)")


def _ensure_inputs_fingerprint_column(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(schedule_runs)").fetchall()
    if not rows:
        return
    names = {str(r[1]) for r in rows}
    if "inputs_fingerprint" not in names:
        conn.execute("ALTER TABLE schedule_runs ADD COLUMN inputs_fingerprint TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS ix_schedule_runs_inputs_fp ON schedule_runs(inputs_fingerprint)",
    )


def _ensure_labor_demand_assigned_column(conn: sqlite3.Connection) -> None:
    rows = conn.execute("PRAGMA table_info(labor_demand_rows)").fetchall()
    if not rows:
        return
    names = {str(r[1]) for r in rows}
    if "assigned_employees" not in names:
        conn.execute("ALTER TABLE labor_demand_rows ADD COLUMN assigned_employees INTEGER DEFAULT 0")


def schedule_cache_debug_counts(db_path: Path) -> tuple[int, int]:
    """
    (число строк schedule_runs, число run_id с хотя бы одной сменой в schedule_assignments).
    Если первое > второе — есть «пустые» прогоны (например, обрыв записи), из-за них кэш мог не находиться.
    """
    if not db_path.is_file():
        return (0, 0)
    conn = sqlite3.connect(str(db_path))
    try:
        total = int(conn.execute("SELECT COUNT(*) FROM schedule_runs").fetchone()[0])
        with_slots = int(
            conn.execute("SELECT COUNT(DISTINCT run_id) FROM schedule_assignments").fetchone()[0]
        )
        return (total, with_slots)
    finally:
        conn.close()


def persist_schedule_run(
    db_path: Path,
    *,
    forecast_digest: str,
    schedule_df: pd.DataFrame,
    labor_demand_df: pd.DataFrame | None,
    meta: dict[str, Any],
    cache_key: str | None = None,
    inputs_fingerprint: str | None = None,
) -> int:
    """
    Insert one run row, schedule slots, optional labor_demand rows.
    Returns run_id.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                forecast_digest TEXT,
                meta_json TEXT NOT NULL,
                cache_key TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schedule_assignments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                ds TEXT,
                station_key TEXT,
                employee_id TEXT,
                starttime TEXT,
                finishtime TEXT,
                FOREIGN KEY (run_id) REFERENCES schedule_runs(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS labor_demand_rows (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                ds TEXT,
                sale_hour INTEGER,
                station_key TEXT,
                required_employees INTEGER,
                assigned_employees INTEGER DEFAULT 0,
                FOREIGN KEY (run_id) REFERENCES schedule_runs(id)
            )
            """
        )
        _ensure_cache_key_column(conn)
        _ensure_inputs_fingerprint_column(conn)
        _ensure_labor_demand_assigned_column(conn)

        meta_out = dict(meta)
        if cache_key is not None:
            meta_out["cache_key"] = cache_key
        if inputs_fingerprint is not None:
            meta_out["inputs_fingerprint"] = inputs_fingerprint

        conn.execute("BEGIN IMMEDIATE")
        try:
            cur = conn.execute(
                "INSERT INTO schedule_runs (created_at, forecast_digest, meta_json, cache_key, inputs_fingerprint) "
                "VALUES (?, ?, ?, ?, ?)",
                (
                    _utc_now_iso(),
                    forecast_digest,
                    json.dumps(meta_out, ensure_ascii=False),
                    cache_key,
                    inputs_fingerprint,
                ),
            )
            run_id = int(cur.lastrowid)

            if not schedule_df.empty:
                rows = []
                for _, r in schedule_df.iterrows():
                    rows.append(
                        (
                            run_id,
                            str(r.get("ds", "")),
                            str(r.get("station_key", "")),
                            str(r.get("employee_id", "")),
                            str(r.get("starttime", "")),
                            str(r.get("finishtime", "")),
                        )
                    )
                conn.executemany(
                    """INSERT INTO schedule_assignments
                    (run_id, ds, station_key, employee_id, starttime, finishtime)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    rows,
                )

            if labor_demand_df is not None and not labor_demand_df.empty:
                ld = labor_demand_df.copy()
                ld.columns = [str(c).strip().lower() for c in ld.columns]
                if "ds" in ld.columns:
                    ld["_ds"] = pd.to_datetime(ld["ds"], errors="coerce").astype(str)
                else:
                    ld["_ds"] = ""
                rows2 = []
                has_asn = "assigned_employees" in ld.columns
                for _, r in ld.iterrows():
                    asn_raw = r["assigned_employees"] if has_asn else 0
                    asn_v = int(asn_raw) if pd.notna(asn_raw) else 0
                    rows2.append(
                        (
                            run_id,
                            str(r.get("_ds", "")),
                            int(r["sale_hour"]) if pd.notna(r.get("sale_hour")) else 0,
                            str(r.get("station_key", "")),
                            int(r["required_employees"])
                            if pd.notna(r.get("required_employees"))
                            else 0,
                            asn_v,
                        )
                    )
                conn.executemany(
                    """INSERT INTO labor_demand_rows
                    (run_id, ds, sale_hour, station_key, required_employees, assigned_employees)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                    rows2,
                )

            conn.commit()
            return run_id
        except Exception:
            conn.rollback()
            raise
    finally:
        conn.close()


def _float_cell(val: object) -> float:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    num = pd.to_numeric(s, errors="coerce")
    if pd.isna(num):
        return 0.0
    return float(num)


def try_load_cached_schedule(
    db_path: Path,
    cache_key: str,
    *,
    inputs_fingerprint: str | None = None,
) -> ScheduleCacheHit | None:
    """
    Загрузка последнего подходящего прогона.

    1) Точное совпадение ``cache_key`` (прогноз + сырьё + спрос + все параметры scheduling).
    2) Иначе, если задан ``inputs_fingerprint`` — последний run с тем же отпечатком входов
       (без лимитов солвера/LNS): удобно при смене «сценария оптимизации» без смены данных.
    """
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_cache_key_column(conn)
        _ensure_inputs_fingerprint_column(conn)
        _ensure_labor_demand_assigned_column(conn)
        match_kind: Literal["exact", "inputs_fingerprint"] = "exact"
        row = conn.execute(
            """
            SELECT sr.id FROM schedule_runs sr
            WHERE sr.cache_key = ?
              AND EXISTS (SELECT 1 FROM schedule_assignments sa WHERE sa.run_id = sr.id LIMIT 1)
            ORDER BY sr.id DESC LIMIT 1
            """,
            (cache_key,),
        ).fetchone()
        if row is None and inputs_fingerprint:
            row = conn.execute(
                """
                SELECT sr.id FROM schedule_runs sr
                WHERE sr.inputs_fingerprint = ?
                  AND sr.inputs_fingerprint IS NOT NULL
                  AND EXISTS (SELECT 1 FROM schedule_assignments sa WHERE sa.run_id = sr.id LIMIT 1)
                ORDER BY sr.id DESC LIMIT 1
                """,
                (inputs_fingerprint,),
            ).fetchone()
            if row is not None:
                match_kind = "inputs_fingerprint"
        if row is None:
            return None
        run_id = int(row[0])

        pair = _load_dataframes_for_run_id(conn, run_id)
        if pair is None:
            return None
        schedule_df, labor_df = pair

        return ScheduleCacheHit(schedule_df, labor_df, run_id, match_kind)
    finally:
        conn.close()


def _load_dataframes_for_run_id(conn: sqlite3.Connection, run_id: int) -> tuple[pd.DataFrame, pd.DataFrame] | None:
    sch_rows = conn.execute(
        """SELECT ds, station_key, employee_id, starttime, finishtime
           FROM schedule_assignments WHERE run_id = ?""",
        (run_id,),
    ).fetchall()
    if not sch_rows:
        return None

    schedule_records: list[dict[str, Any]] = []
    for ds, st, emp, stt, fin in sch_rows:
        schedule_records.append(
            {
                "ds": str(ds),
                "station_key": str(st),
                "employee_id": emp,
                "starttime": _float_cell(stt),
                "finishtime": _float_cell(fin),
            }
        )
    schedule_df = pd.DataFrame(schedule_records)

    ld_rows = conn.execute(
        """SELECT ds, sale_hour, station_key, required_employees, assigned_employees
           FROM labor_demand_rows WHERE run_id = ?""",
        (run_id,),
    ).fetchall()
    if not ld_rows:
        labor_df = pd.DataFrame(
            columns=["ds", "sale_hour", "station_key", "required_employees", "assigned_employees"],
        )
    else:
        labor_records = []
        for ds, sh, sk, rq, asn in ld_rows:
            labor_records.append(
                {
                    "ds": pd.to_datetime(ds, errors="coerce").normalize(),
                    "sale_hour": int(sh),
                    "station_key": str(sk),
                    "required_employees": int(rq),
                    "assigned_employees": int(asn) if asn is not None else 0,
                }
            )
        labor_df = pd.DataFrame(labor_records)

    return schedule_df, labor_df


def load_schedule_run_payload(
    db_path: Path,
    *,
    run_id: int | None = None,
) -> dict[str, Any] | None:
    """
    Загрузка прогона из SQLite для отдачи фронту/API.

    ``run_id=None`` — последний run, у которого есть хотя бы одна смена.
    Возвращает словарь с DataFrame ``schedule_df``, ``labor_df`` и полями метаданных или None.
    """
    if not db_path.is_file():
        return None
    conn = sqlite3.connect(str(db_path))
    try:
        _ensure_cache_key_column(conn)
        _ensure_inputs_fingerprint_column(conn)
        _ensure_labor_demand_assigned_column(conn)

        if run_id is not None:
            meta_row = conn.execute(
                """
                SELECT id, created_at, forecast_digest, cache_key, inputs_fingerprint, meta_json
                FROM schedule_runs WHERE id = ?
                """,
                (int(run_id),),
            ).fetchone()
            if meta_row is None:
                return None
            rid = int(meta_row[0])
            pair = _load_dataframes_for_run_id(conn, rid)
            if pair is None:
                return None
            schedule_df, labor_df = pair
            created_at, digest, ck, ifp, meta_json = (
                meta_row[1],
                meta_row[2],
                meta_row[3],
                meta_row[4],
                meta_row[5],
            )
        else:
            meta_row = conn.execute(
                """
                SELECT sr.id, sr.created_at, sr.forecast_digest, sr.cache_key, sr.inputs_fingerprint, sr.meta_json
                FROM schedule_runs sr
                WHERE EXISTS (SELECT 1 FROM schedule_assignments sa WHERE sa.run_id = sr.id LIMIT 1)
                ORDER BY sr.id DESC LIMIT 1
                """,
            ).fetchone()
            if meta_row is None:
                return None
            rid = int(meta_row[0])
            pair = _load_dataframes_for_run_id(conn, rid)
            if pair is None:
                return None
            schedule_df, labor_df = pair
            created_at, digest, ck, ifp, meta_json = (
                meta_row[1],
                meta_row[2],
                meta_row[3],
                meta_row[4],
                meta_row[5],
            )

        meta_obj: dict[str, Any]
        try:
            meta_obj = json.loads(meta_json) if meta_json else {}
        except json.JSONDecodeError:
            meta_obj = {}

        return {
            "run_id": rid,
            "created_at": created_at,
            "forecast_digest": digest,
            "cache_key": ck,
            "inputs_fingerprint": ifp,
            "meta": meta_obj,
            "schedule_df": schedule_df,
            "labor_df": labor_df,
        }
    finally:
        conn.close()
