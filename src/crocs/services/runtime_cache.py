"""Optional Redis + disk cache for heavy artifacts (e.g. hourly demand parquet)."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from typing import Any

import pandas as pd

REDIS_KEY_PREFIX = "crocs:hourly_demand:"


def connect_redis(url: str | None) -> Any | None:
    """Return a redis client or None if URL missing / redis not installed / connection fails."""
    if not url or not str(url).strip():
        return None
    try:
        import redis  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        client = redis.Redis.from_url(url, decode_responses=False, socket_connect_timeout=2.0)
        client.ping()
        return client
    except Exception:
        return None


def hourly_demand_cache_key(
    *,
    forecast_path: Path | None,
    reqlabor_mtime_ns: int | None,
    morning_split_hour: int,
    forecast_start: str,
    forecast_end: str,
) -> str:
    fp = ""
    if forecast_path is not None and forecast_path.is_file():
        fp = f"{forecast_path.resolve()}:{forecast_path.stat().st_mtime_ns}"
    rel = "" if reqlabor_mtime_ns is None else str(reqlabor_mtime_ns)
    raw = f"{fp}|{rel}|{morning_split_hour}|{forecast_start}|{forecast_end}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def disk_cache_path(cache_dir: Path, key: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{key}.pkl"


def try_load_hourly_demand(
    *,
    redis_client: Any | None,
    use_redis: bool,
    cache_dir: Path | None,
    cache_key: str,
) -> pd.DataFrame | None:
    if use_redis and redis_client is not None:
        try:
            blob = redis_client.get(REDIS_KEY_PREFIX + cache_key)
            if blob:
                return pd.read_pickle(io.BytesIO(blob))
        except Exception:
            pass
    if cache_dir is not None:
        p = disk_cache_path(cache_dir, cache_key)
        if p.is_file():
            return pd.read_pickle(p)
    return None


def store_hourly_demand(
    df: pd.DataFrame,
    *,
    redis_client: Any | None,
    use_redis: bool,
    cache_dir: Path | None,
    cache_key: str,
    ttl_sec: int = 604_800,
) -> None:
    buf = io.BytesIO()
    df.to_pickle(buf)
    data = buf.getvalue()
    if use_redis and redis_client is not None:
        try:
            redis_client.set(REDIS_KEY_PREFIX + cache_key, data, ex=ttl_sec)
        except Exception:
            pass
    if cache_dir is not None:
        path = disk_cache_path(cache_dir, cache_key)
        df.to_pickle(path)
