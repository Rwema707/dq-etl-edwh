from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd

from etl.db import Database, Rollback


def load(db: Database, typed: pd.DataFrame, run_id: str, batch_date: date,
         expected_rows: int | None = None) -> tuple[int, bool]:
    """Idempotent, all-or-nothing load of one batch.

    Replaces any rows previously loaded for `batch_date`, then reconciles the number of rows now in
    the target against `expected_rows`. On mismatch (or any error) the transaction is rolled back.
    Returns (rows_in_target_for_batch, reconciled).
    """
    expected = len(typed) if expected_rows is None else expected_rows
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    cols = ["order_id", "customer_id", "email", "amount", "status", "order_ts"]   # target table shape
    df = pd.DataFrame({c: typed[c] if c in typed.columns else None for c in cols}, index=typed.index)
    df["order_ts"] = df["order_ts"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    df = df.astype(object).where(df.notna(), None)
    rows = [(o, c, e, None if a is None else float(a), s, ts, batch_date.isoformat(), run_id, now)
            for o, c, e, a, s, ts in df.itertuples(index=False, name=None)]

    loaded = 0
    try:
        with db.transaction():
            db.execute("DELETE FROM fact_orders WHERE batch_date = ?", (batch_date.isoformat(),))
            db.executemany(
                "INSERT INTO fact_orders (order_id, customer_id, email, amount, status, order_ts,"
                " batch_date, run_id, loaded_at) VALUES (?,?,?,?,?,?,?,?,?)", rows)
            loaded = db.one("SELECT COUNT(*) AS n FROM fact_orders WHERE batch_date = ? AND run_id = ?",
                            (batch_date.isoformat(), run_id))["n"]
            if loaded != expected:
                raise Rollback
    except Rollback:
        return loaded, False
    return loaded, True
