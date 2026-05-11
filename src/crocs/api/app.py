from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from crocs.services.schedule_animation_export import (
    build_schedule_animation_items,
    schedule_excel_path,
)

DEFAULT_ARTIFACTS = Path(__file__).resolve().parents[3] / "artifacts"


def _artifacts_dir() -> Path:
    raw = os.environ.get("CROCS_ARTIFACTS_DIR", "").strip()
    return Path(raw) if raw else DEFAULT_ARTIFACTS


def create_app() -> FastAPI:
    app = FastAPI(title="crocs schedule API", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/schedule/animation")
    def schedule_animation(
        page: int = 0,
        page_size: int = Query(default=150, alias="pageSize"),
        size: int | None = Query(default=None),
    ) -> JSONResponse:
        ps = size if size is not None else page_size
        ps = max(1, min(ps, 2000))
        page = max(0, page)

        items = build_schedule_animation_items(_artifacts_dir())
        total = len(items)
        start = page * ps
        end = min(start + ps, total)
        chunk = items[start:end]
        has_more = end < total

        return JSONResponse(
            {
                "items": chunk,
                "total": total,
                "page": page,
                "pageSize": ps,
                "hasMore": has_more,
            }
        )

    @app.get("/api/schedule/excel")
    def schedule_excel() -> FileResponse:
        path = schedule_excel_path(_artifacts_dir())
        if not path.is_file():
            raise HTTPException(status_code=404, detail="schedule.xlsx not found")
        return FileResponse(path, filename="schedule.xlsx", media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    host = os.environ.get("CROCS_API_HOST", "127.0.0.1")
    port = int(os.environ.get("CROCS_API_PORT", "8000"))
    uvicorn.run("crocs.api.app:app", host=host, port=port, reload=False)
