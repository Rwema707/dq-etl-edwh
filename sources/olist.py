"""Turn the public Olist e-commerce dataset into daily `orders` batch files.

Olist ships as relational CSVs. We need three of them:
  olist_orders_dataset.csv          order_id, customer_id, order_status, order_purchase_timestamp, ...
  olist_customers_dataset.csv       customer_id, customer_unique_id, ...
  olist_order_payments_dataset.csv  order_id, payment_sequential, payment_type, payment_installments, payment_value

Mapping (nothing is cleaned or dropped here; defects in the source must reach the quality checks):
  order_id   <- orders.order_id
  customer_id<- customers.customer_unique_id   (left join; an unmatched customer stays empty)
  amount     <- sum(payments.payment_value) per order   (an order with no payments stays empty)
  status     <- orders.order_status
  order_ts   <- orders.order_purchase_timestamp (space replaced by 'T')
One file per purchase date: orders_YYYY-MM-DD.csv  (replay: each date is one daily batch).
"""
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

ORDERS, CUSTOMERS, PAYMENTS = ("olist_orders_dataset.csv", "olist_customers_dataset.csv",
                               "olist_order_payments_dataset.csv")
OUT_COLUMNS = ["order_id", "customer_id", "amount", "status", "order_ts"]


def _read(path: Path, usecols: list[str]) -> pd.DataFrame:
    # dtype=str + only empty cells as null = read exactly what was delivered
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], usecols=usecols)


def build_orders(raw_dir: str | Path) -> pd.DataFrame:
    raw = Path(raw_dir)
    orders = _read(raw / ORDERS, ["order_id", "customer_id", "order_status", "order_purchase_timestamp"])
    customers = _read(raw / CUSTOMERS, ["customer_id", "customer_unique_id"])
    pay = _read(raw / PAYMENTS, ["order_id", "payment_value"])

    pay["v"] = pd.to_numeric(pay["payment_value"], errors="coerce")
    totals = pay.groupby("order_id")["v"].sum(min_count=1).round(2)

    df = orders.merge(customers, on="customer_id", how="left")
    amount = df["order_id"].map(totals)
    out = pd.DataFrame({
        "order_id": df["order_id"],
        "customer_id": df["customer_unique_id"],
        "amount": amount.map(lambda v: None if pd.isna(v) else f"{v:.2f}"),
        "status": df["order_status"],
        "order_ts": df["order_purchase_timestamp"].str.replace(" ", "T", regex=False),
    })
    return out.sort_values("order_ts", kind="stable").reset_index(drop=True)[OUT_COLUMNS]


def write_daily_batches(df: pd.DataFrame, out_dir: str | Path, start: date | None = None,
                        end: date | None = None) -> list[date]:
    """Write one CSV per purchase date (inclusive range). Dates with no orders get no file."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    day = df["order_ts"].str.slice(0, 10)
    written = []
    for d, part in df.groupby(day, sort=True):
        try:
            dd = date.fromisoformat(d)
        except ValueError:
            continue   # an unparseable purchase timestamp has no batch to belong to
        if (start and dd < start) or (end and dd > end):
            continue
        part.to_csv(out / f"orders_{d}.csv", index=False)
        written.append(dd)
    return written


def main() -> None:
    p = argparse.ArgumentParser(description="Split the Olist dataset into daily batch files")
    p.add_argument("--raw", default="data/raw/olist", help="folder holding the Olist CSVs")
    p.add_argument("--out", default="data/incoming")
    p.add_argument("--start", type=date.fromisoformat)
    p.add_argument("--end", type=date.fromisoformat)
    a = p.parse_args()
    df = build_orders(a.raw)
    days = write_daily_batches(df, a.out, a.start, a.end)
    print(f"{len(df):,} orders read; wrote {len(days)} daily batch files to {a.out}"
          + (f" ({days[0]} .. {days[-1]})" if days else ""))


if __name__ == "__main__":
    main()
