"""Run the pipeline for every date in a range, oldest first (history builds up exactly as in production).

  python -m etl.backfill --contract contracts/olist_orders.yaml --start 2018-03-01 --end 2018-04-15 --db data/olist.db

Blocked days are expected with real data and do NOT stop the run (they are recorded and shown on the
dashboard). Exit code: 0 normally, 2 if any day crashed unexpectedly.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from dq.contract import load_contract
from etl.db import connect, init_db
from etl.extract import source_path
from etl.run import RunSummary, run_pipeline


def backfill(db, contract: dict, start: date, end: date, data_dir: str,
             skip_missing: bool = True) -> list[tuple[date, RunSummary | None]]:
    results, d = [], start
    while d <= end:
        if skip_missing and not source_path(contract, data_dir, d).exists():
            results.append((d, None))            # no delivery that day; nothing to run
        else:
            results.append((d, run_pipeline(db, contract, d, data_dir)))
        d += timedelta(days=1)
    return results


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Run the ETL over a date range")
    p.add_argument("--contract", default="contracts/orders.yaml")
    p.add_argument("--data-dir", default="data/incoming")
    p.add_argument("--db", default=None, help="SQLite path or postgresql:// URL (default: $DATABASE_URL)")
    p.add_argument("--start", type=date.fromisoformat, required=True)
    p.add_argument("--end", type=date.fromisoformat, required=True)
    p.add_argument("--include-missing", action="store_true",
                   help="also run dates with no source file (recorded as BLOCKED: source missing)")
    a = p.parse_args(argv)
    if a.end < a.start:
        p.error("--end must not be before --start")
    contract, db = load_contract(a.contract), connect(a.db)
    init_db(db)
    results = backfill(db, contract, a.start, a.end, a.data_dir, skip_missing=not a.include_missing)
    counts = {"SUCCESS": 0, "BLOCKED": 0, "ERROR": 0, "no file": 0}
    for d, s in results:
        counts["no file" if s is None else s.status] += 1
        if s is not None and s.status != "SUCCESS":
            fails = db.query("SELECT check_name FROM dq_check_results WHERE run_id=? AND status='FAIL' ORDER BY position",
                             (s.run_id,))
            print(f"{d}  {s.status:8} {', '.join(f['check_name'] for f in fails) or (s.status)}")
    print(f"\n{len(results)} days: " + ", ".join(f"{n} {k}" for k, n in counts.items() if n))
    db.close()
    return 2 if counts["ERROR"] else 0


if __name__ == "__main__":
    sys.exit(main())
