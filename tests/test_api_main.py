from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from crocs.api import main as api_main


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    cfg = tmp_path / "empty.yaml"
    cfg.write_text("project:\n  name: test\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CROCS_CONFIG", str(cfg))
    return TestClient(api_main.app)


def test_health_reports_redis_not_configured(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["redis"] == "not_configured"
    assert body["preload_raw_bundle"] is False


def test_incremental_schedule_returns_501(client: TestClient) -> None:
    r = client.patch("/api/v1/schedule/incremental")
    assert r.status_code == 501


def test_pipeline_job_enqueue_returns_202(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_pipeline(*_a, **_k):
        from types import SimpleNamespace

        import pandas as pd

        return SimpleNamespace(
            forecast=pd.DataFrame({"sale_date": [1], "sale_hour": [2], "guests_count": [3]}),
            warnings=["ok"],
            schedule=None,
            labor_demand=None,
        )

    monkeypatch.setattr(api_main, "run_pipeline", fake_run_pipeline)
    r = client.post("/api/v1/pipeline/jobs", json={})
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    assert len(job_id) >= 8

    st = client.get(f"/api/v1/pipeline/jobs/{job_id}")
    assert st.status_code == 200
    data = st.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("pending", "running", "done", "error")
    # BackgroundTasks in TestClient run after request in same thread
    assert data["status"] == "done"
    assert data["forecast_row_count"] == 1
    assert data["warnings"] == ["ok"]
    assert data["forecast_rows"] is not None and len(data["forecast_rows"]) == 1
    assert data["schedule_rows"] == []
    assert data["labor_demand_rows"] == []
