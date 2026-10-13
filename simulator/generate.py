"""Simulated `orders` source with realistic volumes and switchable defects.

Weekday batches are ~50k rows, weekends ~36k. Amounts are log-normal (skewed), order times
follow a daily curve. Defects are injected on demand so every quality check can be demonstrated.
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

STATUSES = ["PLACED", "PAID", "SHIPPED", "DELIVERED", "CANCELLED"]
STATUS_P = [0.10, 0.15, 0.20, 0.50, 0.05]
_HOUR_W = np.array([1, 1, 1, 1, 1, 2, 3, 4, 5, 6, 6, 6, 7, 7, 6, 6, 6, 7, 8, 8, 7, 5, 3, 2], dtype=float)
HOUR_P = _HOUR_W / _HOUR_W.sum()

KNOWN_DEFECTS = (
    "duplicates", "null_customer", "negative_amount", "bad_status", "bad_amount_text",
    "bad_email", "stale", "volume_drop", "schema_drift",
)


def generate_batch(batch_date: date, n_rows: int | None = None, seed: int | None = None,
                   defects: tuple[str, ...] | list[str] = ()) -> pd.DataFrame:
    """Return one day of orders as an all-string DataFrame (exactly what a CSV would hold)."""
    unknown = set(defects) - set(KNOWN_DEFECTS)
    if unknown:
        raise ValueError(f"unknown defects {sorted(unknown)}; choose from {KNOWN_DEFECTS}")
    rng = np.random.default_rng(batch_date.toordinal() if seed is None else seed)
    if n_rows is None:
        base = 36_000 if batch_date.weekday() >= 5 else 50_000
        n_rows = max(1, int(rng.normal(base, base * 0.03)))

    hours = rng.choice(24, size=n_rows, p=HOUR_P)
    secs = np.sort(hours * 3600 + rng.integers(0, 3600, size=n_rows))
    secs[-1] = 23 * 3600 + 3599                       # guarantee late-evening activity
    ts = pd.Timestamp(batch_date.isoformat()) + pd.to_timedelta(secs, unit="s")
    cust = rng.integers(1, 200_000, size=n_rows)
    df = pd.DataFrame({
        "order_id": [f"ORD-{batch_date:%Y%m%d}-{i:07d}" for i in range(n_rows)],
        "customer_id": [f"C{c:06d}" for c in cust],
        "email": [f"user{c}@example.com" for c in cust],
        "amount": [f"{a:.2f}" for a in np.clip(rng.lognormal(3.5, 0.8, n_rows), 1, 9000)],
        "status": rng.choice(STATUSES, size=n_rows, p=STATUS_P),
        "order_ts": ts.strftime("%Y-%m-%dT%H:%M:%S"),
    }).astype(str)
    return _inject(df, set(defects), rng)


def _inject(df: pd.DataFrame, defects: set[str], rng: np.random.Generator) -> pd.DataFrame:
    def pick(frac: float) -> np.ndarray:
        return rng.choice(len(df), size=max(1, int(len(df) * frac)), replace=False)

    if "null_customer" in defects:
        df.loc[pick(0.02), "customer_id"] = ""
    if "negative_amount" in defects:
        idx = pick(0.003)
        df.loc[idx, "amount"] = "-" + df.loc[idx, "amount"]
    if "bad_status" in defects:
        df.loc[pick(0.01), "status"] = "REFUNDD"
    if "bad_amount_text" in defects:
        df.loc[pick(0.005), "amount"] = "12,50"
    if "bad_email" in defects:
        df.loc[pick(0.02), "email"] = "not-an-email"
    if "stale" in defects:
        df["order_ts"] = (pd.to_datetime(df["order_ts"]) - pd.Timedelta(days=3)).dt.strftime("%Y-%m-%dT%H:%M:%S")
    if "duplicates" in defects:
        df = pd.concat([df, df.iloc[pick(0.005)]], ignore_index=True)
    if "volume_drop" in defects:
        df = df.sample(frac=0.4, random_state=1).sort_index().reset_index(drop=True)
    if "schema_drift" in defects:
        df = df.rename(columns={"amount": "total_amount"})
        df["coupon_code"] = ""
    return df


def write_batch(df: pd.DataFrame, out_dir: str | Path, batch_date: date) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"orders_{batch_date.isoformat()}.csv"
    df.to_csv(path, index=False)
    return path


def main() -> None:
    p = argparse.ArgumentParser(description="Generate a simulated orders batch CSV")
    p.add_argument("--date", required=True, type=date.fromisoformat)
    p.add_argument("--rows", type=int, default=None)
    p.add_argument("--inject", default="", help=f"comma-separated defects: {', '.join(KNOWN_DEFECTS)}")
    p.add_argument("--out", default="data/incoming")
    a = p.parse_args()
    defects = [d for d in a.inject.split(",") if d]
    path = write_batch(generate_batch(a.date, a.rows, defects=defects), a.out, a.date)
    print(f"wrote {path} (defects: {defects or 'none'})")


if __name__ == "__main__":
    main()
