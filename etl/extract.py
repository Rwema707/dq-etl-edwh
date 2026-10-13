from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd


def source_path(contract: dict, data_dir: str | Path, batch_date: date) -> Path:
    name = contract["source"]["file_pattern"].format(batch_date=batch_date.isoformat())
    return Path(data_dir) / name


def extract(contract: dict, data_dir: str | Path, batch_date: date) -> pd.DataFrame:
    """Read the batch exactly as delivered: everything is a string, only empty cells are null."""
    path = source_path(contract, data_dir, batch_date)
    if not path.exists():
        raise FileNotFoundError(f"source file not found: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
