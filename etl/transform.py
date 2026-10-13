from __future__ import annotations

import pandas as pd


def transform(raw: pd.DataFrame, columns: dict) -> pd.DataFrame:
    """Cast to contract types. Values that cannot be cast become NaN/NaT - they are NOT fixed or
    guessed; the `parseable` check reports them and blocks the load."""
    typed = pd.DataFrame(index=raw.index)
    for col, typ in columns.items():
        if col not in raw.columns:
            continue
        if typ == "float":
            typed[col] = pd.to_numeric(raw[col], errors="coerce")
        elif typ == "timestamp":
            typed[col] = pd.to_datetime(raw[col], errors="coerce", format="ISO8601")
        else:
            typed[col] = raw[col]
    return typed
