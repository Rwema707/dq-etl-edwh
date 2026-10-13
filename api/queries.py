"""Read-only queries behind the dashboard. Plain functions so they are easy to test and to
move behind FastAPI later."""
from __future__ import annotations

PILLARS = ("correctness", "completeness", "freshness")


def get_health(conn) -> dict:
    latest = conn.one("SELECT * FROM dq_runs ORDER BY started_at DESC LIMIT 1")
    if latest is None:
        return {"status": "unknown", "latest_run": None, "pillars": {p: "unknown" for p in PILLARS},
                "last_successful_batch": None, "failing_checks": []}
    last_ok = conn.one("SELECT batch_date, finished_at FROM dq_runs WHERE status='SUCCESS' "
                       "ORDER BY started_at DESC LIMIT 1")
    checks = conn.query("SELECT * FROM dq_check_results WHERE run_id=? ORDER BY position", (latest["run_id"],))
    pillars = {}
    for p in PILLARS:
        pc = [c for c in checks if c["pillar"] == p]
        if any(c["status"] == "FAIL" and c["severity"] == "blocking" for c in pc):
            pillars[p] = "fail"
        elif any(c["status"] == "FAIL" for c in pc):
            pillars[p] = "warn"
        elif pc and all(c["status"] == "SKIPPED" for c in pc):
            pillars[p] = "unknown"
        else:
            pillars[p] = "pass" if pc else "unknown"
    status = {"SUCCESS": "degraded" if latest["warnings"] else "healthy", "BLOCKED": "blocked",
              "ERROR": "error", "RUNNING": "running"}[latest["status"]]
    return {"status": status, "latest_run": latest, "pillars": pillars,
            "last_successful_batch": last_ok,
            "failing_checks": [c for c in checks if c["status"] == "FAIL"]}


def list_runs(conn, limit: int = 30) -> list[dict]:
    return conn.query("SELECT * FROM dq_runs ORDER BY started_at DESC LIMIT ?", (limit,))


def get_run(conn, run_id: str) -> dict | None:
    run = conn.one("SELECT * FROM dq_runs WHERE run_id=?", (run_id,))
    if run is None:
        return None
    checks = conn.query("SELECT * FROM dq_check_results WHERE run_id=? ORDER BY position", (run_id,))
    return {"run": run, "checks": checks}


def get_failures(conn, run_id: str, check: str | None = None, limit: int = 50) -> list[dict]:
    sql, args = "SELECT check_name, csv_line, row_json FROM dq_failed_rows WHERE run_id=?", [run_id]
    if check:
        sql, args = sql + " AND check_name=?", args + [check]
    return conn.query(sql + " ORDER BY csv_line LIMIT ?", (*args, limit))
