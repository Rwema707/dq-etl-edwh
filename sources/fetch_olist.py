"""Download the three Olist files this project needs and verify their row counts.

Sources, in order of preference:
  1. --kaggle           uses `kagglehub` (pip install kagglehub); the canonical source, may need Kaggle credentials
  2. --base-url URL     any host serving the files; default is a community Hugging Face mirror
                        (third-party and may disappear: that is why row counts are verified)
Files already present with the right row count are skipped. Run: python -m sources.fetch_olist
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
import urllib.request
from pathlib import Path

DEFAULT_BASE = "https://huggingface.co/visdas/amazon-return-model/resolve/main/data/{name}?download=true"
# Canonical Olist row counts (header excluded)
EXPECTED_ROWS = {
    "olist_orders_dataset.csv": 99_441,
    "olist_customers_dataset.csv": 99_441,
    "olist_order_payments_dataset.csv": 103_886,
}


def count_rows(path: Path) -> int:
    with open(path, newline="", encoding="utf-8") as fh:
        return sum(1 for _ in csv.reader(fh)) - 1


def verify(path: Path, expected: int) -> None:
    got = count_rows(path)
    if got != expected:
        raise ValueError(f"{path.name}: expected {expected:,} rows, found {got:,}")


def download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dq-etl-edwh/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(tmp, "wb") as fh:   # noqa: S310
        shutil.copyfileobj(resp, fh)
    tmp.replace(dest)


def from_kaggle(raw_dir: Path) -> None:
    import kagglehub
    src = Path(kagglehub.dataset_download("olistbr/brazilian-ecommerce"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED_ROWS:
        shutil.copy(src / name, raw_dir / name)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--raw-dir", default="data/raw/olist")
    p.add_argument("--base-url", default=DEFAULT_BASE, help="URL template containing {name}")
    p.add_argument("--kaggle", action="store_true", help="use kagglehub instead of --base-url")
    a = p.parse_args()
    raw = Path(a.raw_dir)
    if a.kaggle:
        from_kaggle(raw)
    for name, expected in EXPECTED_ROWS.items():
        dest = raw / name
        try:
            if not dest.exists():
                print(f"downloading {name} ...")
                download(a.base_url.format(name=name), dest)
            verify(dest, expected)
            print(f"ok  {name}  ({expected:,} rows)")
        except Exception as exc:
            print(f"FAILED {name}: {exc}", file=sys.stderr)
            dest.unlink(missing_ok=True)   # never leave a wrong file that a later run would trust
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
