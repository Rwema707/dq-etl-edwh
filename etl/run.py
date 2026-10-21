"""Pipeline orchestration + CLI.  python -m etl.run --date 2026-10-08

Exit codes: 0 = loaded, 1 = BLOCKED by data quality (nothing loaded), 2 = unexpected ERROR.
"""
from __future__ import annotations

import argparse
import json
import sys
import traceback
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import pandas as pd

from dq.checks import Context, InfrastructureError
from dq.contract import load_contract
from dq.engine import CheckResult, run_checks
from etl.alert import send_alert
from etl.db import Database, connect, init_db
from etl.extract import extract
from etl.load import load
from etl.log import log
from etl.transform import transform


@dataclass
class RunSummary:
    run_id: str
    status: str            # SUCCESS | BLOCKED | ERROR
    source_rows: int = 0
    loaded_rows: int = 0
    blocking_failures: int = 0
    warnings: int = 0

    @property
    def exit_code(self) -> int:
        return {"SUCCESS": 0, "BLOCKED": 1}.get(self.status, 2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _history_depth(contract: dict) -> int:
    """How many earlier batches the checks may look at (weekday mode needs ~7 days per sample)."""
    return max((c.get("window", 7) * (7 if c.get("seasonality") == "weekday" else 1)
                for c in contract["checks"] if c["type"] == "row_count_band"), default=7)


def _history(db: Database, batch_date: date, depth: int, dataset: str) -> list[tuple[date, int]]:
    """(batch_date, rows) of the latest successful run per earlier batch date of this dataset, newest first."""
    rows = db.query("SELECT batch_date, source_rows FROM dq_runs WHERE status='SUCCESS' AND dataset = ?"
                    " AND batch_date < ? ORDER BY batch_date DESC, started_at DESC",
                    (dataset, batch_date.isoformat()))
    seen, out = set(), []
    for r in rows:
        if r["batch_date"] not in seen:
            seen.add(r["batch_date"])
            out.append((date.fromisoformat(r["batch_date"]), r["source_rows"]))
    return out[:depth]


def _target_key_lookup(db: Database, contract: dict, batch_date: date):
    """Keys already in the target from other batches of this dataset (chunked to respect parameter limits)."""
    table, key, dataset = contract["target"]["table"], contract["target"]["key"], contract["dataset"]

    def lookup(values: list[str]) -> set[str]:
        found: set[str] = set()
        vals = sorted(set(values))
        try:
            for i in range(0, len(vals), 1000):
                chunk = vals[i:i + 1000]
                marks = ",".join("?" * len(chunk))
                rows = db.query(f"SELECT {key} AS k FROM {table} WHERE dataset = ? AND batch_date <> ? "
                                f"AND {key} IN ({marks})", (dataset, batch_date.isoformat(), *chunk))
                found.update(r["k"] for r in rows)
        except Exception as exc:
            raise InfrastructureError(f"cannot look up earlier batches in {table}: {exc}") from exc
        return found

    return lookup


def _row_json(row: pd.Series) -> str:
    """A delivered row as strict JSON. Empty cells become null: NaN is not valid JSON and would make
    the stored row unreadable in the dashboard."""
    return json.dumps({k: (None if pd.isna(v) else v) for k, v in row.items()}, allow_nan=False)


def _persist(db: Database, run_id: str, results: list[CheckResult], raw, max_rows: int, start_pos: int = 0) -> None:
    for pos, r in enumerate(results, start=start_pos):
        db.execute("INSERT INTO dq_check_results (run_id, position, check_name, check_type, pillar, severity,"
                   " status, expected, actual, failed_rows, message, hint) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (run_id, pos, r.name, r.type, r.pillar, r.severity, r.status, r.expected, r.actual,
                    r.failed_rows, r.message, r.hint))
        if r.status == "FAIL" and r.failed_idx and raw is not None:
            with db.transaction():
                db.executemany(
                    "INSERT INTO dq_failed_rows (run_id, check_name, csv_line, row_json) VALUES (?,?,?,?)",
                    [(run_id, r.name, int(i) + 2, _row_json(raw.loc[i]))
                     for i in r.failed_idx[:max_rows]])


def _finish(db: Database, run_id: str, status: str, results: list[CheckResult], source_rows=0, loaded_rows=0,
            error: str | None = None) -> RunSummary:
    blocking = sum(r.is_blocking_failure for r in results)
    warnings = sum(r.status == "FAIL" and r.severity == "warning" for r in results)
    db.execute("UPDATE dq_runs SET finished_at=?, status=?, source_rows=?, loaded_rows=?,"
                 " blocking_failures=?, warnings=?, error=? WHERE run_id=?",
                 (_now(), status, source_rows, loaded_rows, blocking, warnings, error, run_id))
    return RunSummary(run_id, status, source_rows, loaded_rows, blocking, warnings)


def run_pipeline(db: Database, contract: dict, batch_date: date, data_dir: str, as_of: datetime | None = None) -> RunSummary:
    run_id = uuid.uuid4().hex[:12]
    as_of = as_of or datetime.combine(batch_date + timedelta(days=1), time(6, 0))  # simulated 06:00 UTC run
    db.execute("INSERT INTO dq_runs (run_id, batch_date, started_at, status, dataset) VALUES (?,?,?, 'RUNNING', ?)",
               (run_id, batch_date.isoformat(), _now(), contract["dataset"]))
    log("INFO", "run_started", run_id=run_id, batch_date=batch_date)
    max_rows = contract.get("max_failed_rows_stored", 100)
    try:
        try:
            raw = extract(contract, data_dir, batch_date)
        except FileNotFoundError as exc:
            res = [CheckResult("source_available", "source", "freshness", "blocking", "FAIL", "batch file present",
                               "file missing", 0, str(exc),
                               "The source file never arrived. Check the upstream export job, then rerun.")]
            _persist(db, run_id, res, None, max_rows)
            s = _finish(db, run_id, "BLOCKED", res)
            send_alert(f"[DQ] BLOCKED batch {batch_date}: {exc}")
            return s

        typed = transform(raw, contract["columns"])
        ctx = Context(raw, typed, contract["columns"],
                      _history(db, batch_date, _history_depth(contract), contract["dataset"]), as_of, batch_date,
                      _target_key_lookup(db, contract, batch_date))
        results = run_checks(contract, ctx)
        _persist(db, run_id, results, raw, max_rows)
        for r in results:
            log("ERROR" if r.is_blocking_failure else "WARNING" if r.status == "FAIL" else "INFO",
                "check_result", run_id=run_id, check=r.name, status=r.status, severity=r.severity,
                failed_rows=r.failed_rows, message=r.message)

        failing = [r for r in results if r.is_blocking_failure]
        if failing:
            s = _finish(db, run_id, "BLOCKED", results, source_rows=len(raw))
            send_alert(f"[DQ] BLOCKED batch {batch_date}: {len(failing)} blocking check(s) failed: "
                       + ", ".join(r.name for r in failing) + f" (run {run_id}). Nothing was loaded.")
            return s

        loaded, ok = load(db, typed, run_id, batch_date, expected_rows=len(raw), dataset=contract["dataset"])
        rec = CheckResult("source_equals_loaded", "reconciliation", "completeness", "blocking",
                          "PASS" if ok else "FAIL", f"{len(raw)} rows in target", f"{loaded} rows in target",
                          0, "" if ok else "row count mismatch after load; transaction rolled back",
                          "Load did not reconcile with the source file. Rerun; if it repeats, inspect the target table.")
        _persist(db, run_id, [rec], None, max_rows, start_pos=len(results))
        results.append(rec)
        if not ok:
            s = _finish(db, run_id, "BLOCKED", results, source_rows=len(raw))
            send_alert(f"[DQ] BLOCKED batch {batch_date}: load did not reconcile (run {run_id}). Rolled back.")
            return s
        s = _finish(db, run_id, "SUCCESS", results, source_rows=len(raw), loaded_rows=loaded)
        log("INFO", "run_succeeded", run_id=run_id, loaded=loaded, warnings=s.warnings)
        return s
    except Exception as exc:
        tb = traceback.format_exc()
        s = _finish(db, run_id, "ERROR", [], error=f"{type(exc).__name__}: {exc}")
        log("ERROR", "run_crashed", run_id=run_id, error=str(exc), traceback=tb)
        send_alert(f"[DQ] ERROR batch {batch_date}: {type(exc).__name__}: {exc} (run {run_id})")
        return s


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the orders ETL for one batch date")
    p.add_argument("--date", type=date.fromisoformat, default=datetime.now(timezone.utc).date())
    p.add_argument("--contract", default="contracts/orders.yaml")
    p.add_argument("--data-dir", default="data/incoming")
    p.add_argument("--db", default=None, help="SQLite path or postgresql:// URL (default: $DATABASE_URL, $DQ_DB_PATH)")
    p.add_argument("--as-of", type=datetime.fromisoformat, default=None, help="reference time for freshness (UTC)")
    a = p.parse_args(argv)
    contract = load_contract(a.contract)
    db = connect(a.db)
    init_db(db)
    s = run_pipeline(db, contract, a.date, a.data_dir, a.as_of)
    print(f"\nrun {s.run_id}  batch {a.date}  -> {s.status}  "
          f"(source {s.source_rows:,} rows, loaded {s.loaded_rows:,}, "
          f"blocking failures {s.blocking_failures}, warnings {s.warnings})")
    if s.status != "SUCCESS":
        for r in db.query("SELECT check_name, message FROM dq_check_results WHERE run_id=? AND status='FAIL' ORDER BY position", (s.run_id,)):
            print(f"  FAIL {r['check_name']}: {r['message']}")
        print(f"  details: dashboard run {s.run_id}")
    db.close()
    return s.exit_code


if __name__ == "__main__":
    sys.exit(main())
