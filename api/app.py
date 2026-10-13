"""Production API (FastAPI).   uvicorn api.app:app --port 8000

Read-only. Interactive docs at /docs. Serves the built dashboard (dashboard/dist) when present, so
one process can host both locally; in production the dashboard is usually hosted separately and
this service only needs CORS_ORIGINS set to the dashboard's URL.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import queries
from etl.db import Database, connect

DASH = Path(__file__).resolve().parent.parent / "dashboard"
DIST, LEGACY = DASH / "dist", DASH / "legacy.html"

app = FastAPI(title="Data health API", version="1.0.0",
              description="Read-only view of ETL runs, data quality check results and failing rows.")

origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["GET"], allow_headers=[])


def get_db():
    try:
        db = connect(readonly=True)
    except Exception as exc:
        raise HTTPException(503, "database unavailable - check DATABASE_URL and that the pipeline has run") from exc
    try:
        yield db
    finally:
        db.close()


@app.get("/healthz", include_in_schema=False)
def healthz() -> dict:
    """Liveness probe for the host (does not touch the database)."""
    return {"ok": True}


@app.get("/api/health")
def health(db: Database = Depends(get_db)) -> dict:
    """Overall status, per-pillar status and the checks failing in the latest run."""
    return queries.get_health(db)


@app.get("/api/runs")
def runs(limit: int = Query(30, ge=1, le=200), db: Database = Depends(get_db)) -> list[dict]:
    """Most recent runs first."""
    return queries.list_runs(db, limit)


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str, db: Database = Depends(get_db)) -> dict:
    found = queries.get_run(db, run_id)
    if found is None:
        raise HTTPException(404, "run not found")
    return found


@app.get("/api/runs/{run_id}/failures")
def run_failures(run_id: str, check: str | None = None, limit: int = Query(50, ge=1, le=200),
                 db: Database = Depends(get_db)) -> list[dict]:
    """Stored failing rows (as delivered), optionally for one check."""
    return queries.get_failures(db, run_id, check, limit)


if DIST.exists():
    app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")
else:
    @app.get("/", include_in_schema=False)
    def legacy_dashboard() -> FileResponse:
        return FileResponse(LEGACY)
