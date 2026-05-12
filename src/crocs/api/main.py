from __future__ import annotations

import json
import os
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from crocs.config import GuestsSource, load_settings
from crocs.services.pipeline_service import run_pipeline

JobStatus = Literal["pending", "running", "done", "error"]


def _dataframe_json_records(df: pd.DataFrame | None) -> list[dict[str, Any]]:
    """Сериализация таблицы для JSON (даты ISO, NaN → null)."""
    if df is None or df.empty:
        return []
    blob = df.to_json(orient="records", date_format="iso")
    return json.loads(blob)


class ForecastPipelineResponse(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    forecast_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Строки прогноза: sale_date, sale_hour, guests_count",
    )
    schedule_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Смены: ds, station_key, employee_id, starttime, finishtime",
    )
    labor_demand_rows: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Потребность по слотам: ds, sale_hour, station_key, required_employees, assigned_employees",
    )


class PipelineJobRequest(BaseModel):
    """Параметры фонового прогона (пути относительно cwd сервера)."""

    data_dir: str = Field(default="data/raw", description="Каталог ML: train, weather, reqlabor…")
    forecast_input_dir: str = Field(
        default="data/output",
        description="Каталог для forecast.xlsx при guests_source=file",
    )
    artifacts_dir: str = Field(default="artifacts", description="Каталог артефактов")
    config: str | None = Field(
        default=None,
        description="YAML конфиг; по умолчанию configs/default.yaml",
    )
    guests_source: GuestsSource | None = Field(
        default=None,
        description="Переопределить forecast.guests_source",
    )


class PipelineJobAccepted(BaseModel):
    job_id: str
    status: JobStatus = "pending"


class PipelineJobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    detail: str | None = None
    warnings: list[str] = Field(default_factory=list)
    forecast_row_count: int | None = None
    schedule_row_count: int | None = None
    labor_demand_row_count: int | None = None
    forecast_rows: list[dict[str, Any]] | None = Field(
        default=None,
        description="Заполняется при status=done",
    )
    schedule_rows: list[dict[str, Any]] | None = Field(
        default=None,
        description="Заполняется при status=done",
    )
    labor_demand_rows: list[dict[str, Any]] | None = Field(
        default=None,
        description="Заполняется при status=done",
    )


_job_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _resolve_cwd_path(s: str) -> Path:
    p = Path(s)
    if p.is_absolute():
        raise HTTPException(
            status_code=400,
            detail="Укажите относительный путь от каталога запуска сервера.",
        )
    return (Path.cwd() / p).resolve()


def _workspace_path_allow_absolute(s: str) -> Path:
    """Путь от cwd или абсолютный (для CROCS_CONFIG / CROCS_PRELOAD_RAW_DIR на lifespan)."""
    p = Path(s.strip())
    if p.is_absolute():
        return p.resolve()
    return (Path.cwd() / p).resolve()


def _config_path_from_env() -> Path:
    raw = os.environ.get("CROCS_CONFIG", "configs/default.yaml").strip()
    return _workspace_path_allow_absolute(raw)


def _run_pipeline_job(
    job_id: str,
    *,
    data_dir: Path,
    artifacts_dir: Path,
    config_path: Path | None,
    forecast_input_dir: Path,
    guests_source: GuestsSource | None,
) -> None:
    with _job_lock:
        _jobs[job_id]["status"] = "running"
        _jobs[job_id]["detail"] = None
    try:
        result = run_pipeline(
            data_dir,
            artifacts_dir,
            config_path=config_path,
            forecast_input_dir=forecast_input_dir,
            guests_source=guests_source,
        )
        sched_n = len(result.schedule) if result.schedule is not None else None
        ld_n = len(result.labor_demand) if result.labor_demand is not None else None
        forecast_rows = _dataframe_json_records(result.forecast)
        schedule_rows = _dataframe_json_records(result.schedule)
        labor_demand_rows = _dataframe_json_records(result.labor_demand)
        with _job_lock:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["warnings"] = list(result.warnings)
            _jobs[job_id]["forecast_row_count"] = len(result.forecast)
            _jobs[job_id]["schedule_row_count"] = sched_n
            _jobs[job_id]["labor_demand_row_count"] = ld_n
            _jobs[job_id]["forecast_rows"] = forecast_rows
            _jobs[job_id]["schedule_rows"] = schedule_rows
            _jobs[job_id]["labor_demand_rows"] = labor_demand_rows
            _jobs[job_id]["detail"] = None
    except Exception as exc:
        with _job_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["detail"] = str(exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg_path = _config_path_from_env()
    app.state.config_path = cfg_path
    app.state.settings = load_settings(cfg_path)

    preload_raw = os.environ.get("CROCS_PRELOAD_RAW_DIR", "").strip()
    if preload_raw:
        try:
            from crocs.io.csv_repository import load_raw_bundle

            raw_dir = _workspace_path_allow_absolute(preload_raw)
            app.state.preloaded_bundle = load_raw_bundle(raw_dir)
        except Exception:
            app.state.preloaded_bundle = None
    else:
        app.state.preloaded_bundle = None

    yield


app = FastAPI(
    title="Crocs",
    description="ML-прогноз почасового числа гостей; расписание CP-SAT + LNS.",
    version="0.1.0",
    lifespan=lifespan,
)

_origins = os.environ.get("CROCS_CORS_ORIGINS", "*").strip()
_cors_list = [o.strip() for o in _origins.split(",") if o.strip()] or ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _relative_path(s: str) -> Path:
    return _resolve_cwd_path(s)


@app.get("/health")
def health(request: Request) -> dict[str, object]:
    st = request.app.state
    preload = getattr(st, "preloaded_bundle", None)
    redis_status = getattr(st, "redis_status", None)
    if redis_status is None:
        redis_status = "not_configured"
    return {
        "status": "ok",
        "config_resolved": str(getattr(st, "config_path", "")),
        "preload_raw_bundle": preload is not None,
        "redis": redis_status,
    }


@app.get("/api/v1/forecast-pipeline", response_model=ForecastPipelineResponse)
def forecast_pipeline(
    data_dir: str = Query("data/raw", description="Каталог для ML: train, weather"),
    forecast_input_dir: str = Query(
        "data/output",
        description="Каталог для forecast.xlsx при guests_source=file",
    ),
    artifacts_dir: str = Query("artifacts", description="Каталог для артефактов прогона"),
    config: str | None = Query(
        None,
        description="YAML конфиг (по умолчанию configs/default.yaml относительно cwd)",
    ),
    guests_source: Annotated[
        GuestsSource | None,
        Query(
            description=(
                "Переопределить forecast.guests_source: file — forecast.xlsx; model — train."
            ),
        ),
    ] = None,
) -> ForecastPipelineResponse:
    """Полный пайплайн (как CLI): прогноз, при включённом scheduling — расписание и labor demand в JSON + файлы в artifacts."""
    dd = _relative_path(data_dir)
    fd = _relative_path(forecast_input_dir)
    ad = _relative_path(artifacts_dir)
    cfg_path = _relative_path(config) if config else None
    try:
        result = run_pipeline(
            dd,
            ad,
            config_path=cfg_path,
            forecast_input_dir=fd,
            guests_source=guests_source,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ForecastPipelineResponse(
        warnings=result.warnings,
        forecast_rows=_dataframe_json_records(result.forecast),
        schedule_rows=_dataframe_json_records(result.schedule),
        labor_demand_rows=_dataframe_json_records(result.labor_demand),
    )


@app.post("/api/v1/pipeline/jobs", response_model=PipelineJobAccepted, status_code=202)
def enqueue_pipeline_job(
    body: PipelineJobRequest,
    background_tasks: BackgroundTasks,
) -> PipelineJobAccepted:
    """Ставит полный пайплайн в очередь FastAPI BackgroundTasks (после ответа 202)."""
    job_id = uuid.uuid4().hex[:16]
    dd = _relative_path(body.data_dir)
    ad = _relative_path(body.artifacts_dir)
    fd = _relative_path(body.forecast_input_dir)
    cfg_path = _relative_path(body.config) if body.config else None
    with _job_lock:
        _jobs[job_id] = {
            "status": "pending",
            "detail": None,
            "warnings": [],
            "forecast_row_count": None,
            "schedule_row_count": None,
            "labor_demand_row_count": None,
            "forecast_rows": None,
            "schedule_rows": None,
            "labor_demand_rows": None,
        }
    background_tasks.add_task(
        _run_pipeline_job,
        job_id,
        data_dir=dd,
        artifacts_dir=ad,
        config_path=cfg_path,
        forecast_input_dir=fd,
        guests_source=body.guests_source,
    )
    return PipelineJobAccepted(job_id=job_id, status="pending")


@app.get("/api/v1/pipeline/jobs/{job_id}", response_model=PipelineJobStatusResponse)
def pipeline_job_status(job_id: str) -> PipelineJobStatusResponse:
    with _job_lock:
        row = _jobs.get(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Неизвестный job_id")
    return PipelineJobStatusResponse(
        job_id=job_id,
        status=row["status"],
        detail=row.get("detail"),
        warnings=list(row.get("warnings") or []),
        forecast_row_count=row.get("forecast_row_count"),
        schedule_row_count=row.get("schedule_row_count"),
        labor_demand_row_count=row.get("labor_demand_row_count"),
        forecast_rows=row.get("forecast_rows"),
        schedule_rows=row.get("schedule_rows"),
        labor_demand_rows=row.get("labor_demand_rows"),
    )


@app.patch("/api/v1/schedule/incremental")
def schedule_incremental_patch() -> None:
    """Зарезервировано: частичное обновление расписания без полного пересчёта горизонта."""
    raise HTTPException(
        status_code=501,
        detail="Инкрементальное обновление расписания пока не реализовано.",
    )


def run_server() -> None:
    """Точка входа: ``crocs-api`` или ``python -m crocs.api.main``."""
    import uvicorn

    host = os.environ.get("CROCS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CROCS_API_PORT", "8000"))
    uvicorn.run("crocs.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
