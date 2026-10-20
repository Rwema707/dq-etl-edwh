"""Read-only queries behind the dashboard. Plain functions so they are easy to test and to
move behind FastAPI later. Every view is scoped to one dataset; when none is named, the dataset
of the most recent run is used."""
from __future__ import annotations

PILLARS = ("correctness", "completeness", "freshness")


def overall_status(run: dict) -> str:
    return {"SUCCESS": "degraded" if run["warnings"] else "healthy", "BLOCKED": "blocked",
            "ERROR": "error", "RUNNING": "running"}[run["status"]]


def latest_dataset(db) -> str | None:
    row = db.one("SELECT dataset FROM dq_runs ORDER BY started_at DESC LIMIT 1")
    return row["dataset"] if row else None


def list_datasets(db) -> list[dict]:
    """Every dataset that has run, most recently active first, with its current overall status."""
    rows = db.query("SELECT dataset, COUNT(*) AS runs, MAX(started_at) AS last_run_at FROM dq_runs "
                    "GROUP BY dataset ORDER BY last_run_at DESC")
    for r in rows:
        latest = db.one("SELECT status, warnings FROM dq_runs WHERE dataset = ? ORDER BY started_at DESC LIMIT 1",
                        (r["dataset"],))
        r["status"] = overall_status(latest)
    return rows


def get_health(db, dataset: str | None = None) -> dict:
    dataset = dataset or latest_dataset(db)
    latest = db.one("SELECT * FROM dq_runs WHERE dataset = ? ORDER BY started_at DESC LIMIT 1", (dataset,)) \
        if dataset else None
    if latest is None:
        return {"dataset": dataset, "status": "unknown", "latest_run": None,
                "pillars": {p: "unknown" for p in PILLARS}, "last_successful_batch": None, "failing_checks": []}
    last_ok = db.one("SELECT batch_date, finished_at FROM dq_runs WHERE status='SUCCESS' AND dataset = ? "
                     "ORDER BY started_at DESC LIMIT 1", (dataset,))
    checks = db.query("SELECT * FROM dq_check_results WHERE run_id=? ORDER BY position", (latest["run_id"],))
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
    return {"dataset": dataset, "status": overall_status(latest), "latest_run": latest, "pillars": pillars,
            "last_successful_batch": last_ok, "failing_checks": [c for c in checks if c["status"] == "FAIL"]}


def list_runs(db, limit: int = 30, dataset: str | None = None) -> list[dict]:
    dataset = dataset or latest_dataset(db)
    if dataset is None:
        return []
    return db.query("SELECT * FROM dq_runs WHERE dataset = ? ORDER BY started_at DESC LIMIT ?", (dataset, limit))


def get_run(db, run_id: str) -> dict | None:
    run = db.one("SELECT * FROM dq_runs WHERE run_id=?", (run_id,))
    if run is None:
        return None
    checks = db.query("SELECT * FROM dq_check_results WHERE run_id=? ORDER BY position", (run_id,))
    return {"run": run, "checks": checks}


def get_failures(db, run_id: str, check: str | None = None, limit: int = 50) -> list[dict]:
    sql, args = "SELECT check_name, csv_line, row_json FROM dq_failed_rows WHERE run_id=?", [run_id]
    if check:
        sql, args = sql + " AND check_name=?", args + [check]
    return db.query(sql + " ORDER BY csv_line LIMIT ?", (*args, limit))
