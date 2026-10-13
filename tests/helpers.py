import os
import tempfile
from datetime import date, timedelta
from pathlib import Path

from dq.contract import load_contract
from etl.db import connect, init_db
from etl.run import run_pipeline
from simulator.generate import generate_batch, write_batch

ROOT = Path(__file__).resolve().parent.parent
D0 = date(2026, 10, 1)


class Env:
    """Throw-away DB + data dir for one test.

    SQLite temp file by default. Set TEST_DATABASE_URL=postgresql://... to run the identical
    tests against Postgres (tables are dropped and recreated for every test)."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.url = os.environ.get("TEST_DATABASE_URL")
        self.db = connect(self.url or str(self.dir / "t.db"))
        if self.url:
            self.db.drop_all()
        init_db(self.db)
        self.contract = load_contract(ROOT / "contracts" / "orders.yaml")

    def day(self, i):
        return D0 + timedelta(days=i)

    def run(self, i, defects=(), rows=300, write=True):
        if write:
            write_batch(generate_batch(self.day(i), rows, defects=defects), self.dir, self.day(i))
        return run_pipeline(self.db, self.contract, self.day(i), str(self.dir))

    def seed_history(self, days=4):
        for i in range(days):
            assert self.run(i).status == "SUCCESS"

    def count(self, i):
        return self.db.one("SELECT COUNT(*) AS n FROM fact_orders WHERE batch_date=?",
                           (self.day(i).isoformat(),))["n"]

    def check_status(self, run_id, name):
        r = self.db.one("SELECT status FROM dq_check_results WHERE run_id=? AND check_name=?",
                        (run_id, name))
        return r["status"] if r else None

    def close(self):
        self.db.close()
        self.tmp.cleanup()
