from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from crocs.config import load_settings
from crocs.services.pipeline_service import run_pipeline
from crocs.services.staffing_dashboard import StaffingGridResponse, build_staffing_grid

app = FastAPI(
    title="Crocs",
    description="Прогноз гостей и расписание: агрегированная сетка для UI.",
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


@app.get("/api/v1/staffing-grid", response_model=StaffingGridResponse)
def get_staffing_grid(
    data_dir: str = Query("data/raw", description="Каталог с входными CSV/XLSX"),
    artifacts_dir: str = Query("artifacts", description="Каталог для сохранения артефактов прогона"),
    config: str | None = Query(
        None,
        description="YAML конфиг (по умолчанию configs/default.yaml относительно cwd)",
    ),
) -> StaffingGridResponse:
    """
    Запускает полный пайплайн (прогноз + спрос + CP-SAT) и возвращает плоскую таблицу по
    дате, часу и станции: гости, норматив, назначено, список сотрудников, индикатор покрытия.
    """
    dd = _relative_path(data_dir)
    ad = _relative_path(artifacts_dir)
    cfg_path = _relative_path(config) if config else None
    try:
        result = run_pipeline(dd, ad, config_path=cfg_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    cfg_file = cfg_path if cfg_path is not None else Path("configs/default.yaml")
    if not cfg_file.is_file():
        cfg_file = Path("configs/default.yaml")
    settings = load_settings(cfg_file)

    return build_staffing_grid(
        result.forecast,
        result.labor_demand,
        result.schedule,
        open_hour=settings.forecast.open_hour,
        close_hour=settings.forecast.close_hour,
        warnings=result.warnings,
    )


def run_server() -> None:
    """Точка входа: ``crocs-api`` или ``python -m crocs.api.main``."""
    import uvicorn

    host = os.environ.get("CROCS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CROCS_API_PORT", "8000"))
    uvicorn.run("crocs.api.main:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    run_server()
