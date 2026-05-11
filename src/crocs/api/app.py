"""Легаси-точка входа ``crocs-api``: то же приложение, что ``crocs.api.main``."""

from __future__ import annotations

from crocs.api.main import app, run_server


def run() -> None:
    run_server()
