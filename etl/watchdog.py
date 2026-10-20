"""Alert when the pipeline has not run at all (a missed schedule produces no failure to notice).

  python -m etl.watchdog --max-age-hours 26      exit 0 = a run was recorded recently, 1 = stale/none (alert sent)
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from etl.alert import send_alert
from etl.db import Database, connect


def check_recent_run(db: Database, now: datetime, max_age_hours: float,
                     dataset: str | None = None) -> tuple[bool, str]:
    where, args = ("WHERE dataset = ? ", (dataset,)) if dataset else ("", ())
    latest = db.one("SELECT run_id, batch_date, started_at, status FROM dq_runs " + where
                    + "ORDER BY started_at DESC LIMIT 1", args)
    if latest is None:
        return False, "no pipeline run has ever been recorded" + (f" for dataset '{dataset}'" if dataset else "")
    age_h = (now - datetime.fromisoformat(latest["started_at"])).total_seconds() / 3600
    detail = f"latest run {latest['run_id']} (batch {latest['batch_date']}, {latest['status']}) started {age_h:.1f}h ago"
    if age_h > max_age_hours:
        return False, f"{detail}; limit is {max_age_hours:g}h"
    return True, detail


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--max-age-hours", type=float, default=26)
    p.add_argument("--dataset", default=None, help="only look at runs of this dataset (default: any)")
    p.add_argument("--db", default=None)
    a = p.parse_args(argv)
    db = connect(a.db)
    try:
        ok, msg = check_recent_run(db, datetime.now(timezone.utc), a.max_age_hours, a.dataset)
    finally:
        db.close()
    print(("OK: " if ok else "STALE: ") + msg)
    if not ok:
        send_alert(f"[DQ] watchdog: no recent pipeline run. {msg}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
