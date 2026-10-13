"""Populate a demo history: python -m simulator.seed_demo [--rows 5000]

Story: 7 clean days -> a warning-only day -> duplicates blocked, then fixed upstream and rerun
-> final day blocked by two defects (so the dashboard opens on a failure worth diagnosing).
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta

from dq.contract import load_contract
from etl.db import connect, init_db
from etl.run import run_pipeline
from simulator.generate import generate_batch, write_batch


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rows", type=int, default=5000)
    p.add_argument("--data-dir", default="data/incoming")
    p.add_argument("--db", default=None, help="SQLite path or postgresql:// URL")
    a = p.parse_args()
    contract, db = load_contract("contracts/orders.yaml"), connect(a.db)
    init_db(db)
    start = date.today() - timedelta(days=10)

    def step(i, defects=()):
        d = start + timedelta(days=i)
        write_batch(generate_batch(d, a.rows, defects=defects), a.data_dir, d)
        s = run_pipeline(db, contract, d, a.data_dir)
        print(f"{d}  {defects or 'clean'!s:45} -> {s.status}")

    for i in range(7):
        step(i)
    step(7, ["bad_email"])
    step(8, ["duplicates"])
    step(8)                                   # upstream fixed the file, rerun succeeds
    step(9, ["null_customer", "negative_amount"])


if __name__ == "__main__":
    main()
