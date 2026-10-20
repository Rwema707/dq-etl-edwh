"""Zero-dependency fallback API + dashboard host (SQLite or Postgres). The production API is api/app.py (FastAPI).  python -m api.server --port 8000

Endpoints: /  /api/datasets  /api/health[?dataset=]  /api/runs[?dataset=&limit=]  /api/runs/<id>  /api/runs/<id>/failures?check=<name>
"""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from api import queries
from etl.db import connect

DASH = Path(__file__).resolve().parent.parent / "dashboard"
DIST = DASH / "dist"          # created by `npm run build` in dashboard/
LEGACY = DASH / "legacy.html"  # zero-build fallback used when dist/ does not exist
MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript", ".css": "text/css",
        ".svg": "image/svg+xml", ".json": "application/json", ".woff2": "font/woff2", ".ico": "image/x-icon"}


class Handler(BaseHTTPRequestHandler):
    db_path: str | None = None

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload, code: int = 200) -> None:
        self._send(code, json.dumps(payload, default=str).encode(), "application/json")

    def _static(self, parts: list[str]) -> None:
        if not DIST.exists():
            if parts:
                return self._json({"error": "not found"}, 404)
            return self._send(200, LEGACY.read_bytes(), MIME[".html"])
        target = (DIST.joinpath(*parts) if parts else DIST / "index.html").resolve()
        if DIST.resolve() not in target.parents:   # block path traversal
            return self._json({"error": "not found"}, 404)
        if not target.is_file():
            return self._json({"error": "not found"}, 404)
        self._send(200, target.read_bytes(), MIME.get(target.suffix, "application/octet-stream"))

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        parts = [p for p in url.path.split("/") if p]
        if not parts or parts[0] != "api":
            return self._static(parts)
        try:
            conn = connect(self.db_path, readonly=True)
        except Exception:
            return self._json({"error": "database unavailable - run the pipeline first"}, 503)
        try:
            qs = parse_qs(url.query)
            dataset = qs.get("dataset", [None])[0]
            if parts[1:] == ["datasets"]:
                return self._json(queries.list_datasets(conn))
            if parts[1:] == ["health"]:
                return self._json(queries.get_health(conn, dataset))
            if parts[1:] == ["runs"]:
                raw = qs.get("limit", ["30"])[0]
                limit = min(int(raw), 200) if raw.isdigit() else 30
                return self._json(queries.list_runs(conn, limit, dataset))
            if len(parts) == 3 and parts[1] == "runs":
                run = queries.get_run(conn, parts[2])
                return self._json(run) if run else self._json({"error": "run not found"}, 404)
            if len(parts) == 4 and parts[1] == "runs" and parts[3] == "failures":
                check = qs.get("check", [None])[0]
                return self._json(queries.get_failures(conn, parts[2], check))
            return self._json({"error": "not found"}, 404)
        finally:
            conn.close()

    def log_message(self, *args) -> None:  # keep console quiet
        pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--db", default=None)
    a = p.parse_args()
    Handler.db_path = a.db
    print(f"dashboard on http://localhost:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
