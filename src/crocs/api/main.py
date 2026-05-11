from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from crocs.config import GuestsSource
from crocs.services.pipeline_service import run_pipeline


class ForecastPipelineResponse(BaseModel):
    warnings: list[str] = Field(default_factory=list)
    forecast_rows: list[dict[str, object]] = Field(
        default_factory=list,
        description="Строки прогноза: sale_date, sale_hour, guests_count",
    )


app = FastAPI(
    title="Crocs",
    description="ML-прогноз почасового числа гостей.",
    version="0.1.0",
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
    p = Path(s)
    if p.is_absolute():
        raise HTTPException(status_code=400, detail="Укажите относительный путь от каталога запуска сервера.")
    return (Path.cwd() / p).resolve()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/forecast-pipeline", response_model=ForecastPipelineResponse)
def forecast_pipeline(
    data_dir: str = Query("data/raw", description="Каталог для ML: train, weather"),
    forecast_input_dir: str = Query(
        "data/output",
        description="Каталог с forecast.xlsx при guests_source=file",
    ),
    artifacts_dir: str = Query("artifacts", description="Каталог для артефактов прогона"),
    config: str | None = Query(
        None,
        description="YAML конфиг (по умолчанию configs/default.yaml относительно cwd)",
    ),
    guests_source: GuestsSource | None = Query(
        None,
        description="Переопределить forecast.guests_source: file — forecast.xlsx; model — train.",
    ),
) -> ForecastPipelineResponse:
    """Запускает пайплайн прогноза гостей и возвращает таблицу прогноза."""
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

    rows = result.forecast.to_dict(orient="records")
    return ForecastPipelineResponse(warnings=result.warnings, forecast_rows=rows)


def run_server() -> None:
    """Точка входа: ``crocs-api`` или ``python -m crocs.api.main``."""
    import uvicorn

    host = os.environ.get("CROCS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CROCS_API_PORT", "8000"))
    uvicorn.run("crocs.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
