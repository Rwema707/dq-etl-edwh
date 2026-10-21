"""Load and validate a data contract. A bad contract fails at startup, not mid-run."""
from __future__ import annotations

from datetime import date
from pathlib import Path

import yaml

from dq.checks import CHECKS

PILLARS = {"correctness", "completeness", "freshness"}
SEVERITIES = {"blocking", "warning"}
COLUMN_TYPES = {"string", "float", "timestamp"}


def load_contract(path: str | Path) -> dict:
    contract = yaml.safe_load(Path(path).read_text())
    for key in ("dataset", "source", "target", "columns", "checks"):
        if key not in contract:
            raise ValueError(f"contract missing '{key}'")
    for col, typ in contract["columns"].items():
        if typ not in COLUMN_TYPES:
            raise ValueError(f"column '{col}' has unsupported type '{typ}'")
    names = set()
    for spec in contract["checks"]:
        name = spec.get("name")
        if not name or name in names:
            raise ValueError(f"check name missing or duplicated: {name!r}")
        names.add(name)
        if spec.get("type") not in CHECKS:
            raise ValueError(f"check '{name}': unknown type {spec.get('type')!r}")
        if spec.get("pillar") not in PILLARS:
            raise ValueError(f"check '{name}': pillar must be one of {sorted(PILLARS)}")
        if spec.get("severity") not in SEVERITIES:
            raise ValueError(f"check '{name}': severity must be one of {sorted(SEVERITIES)}")
        _validate_known_events(name, spec.get("known_events", []))
        for col in [spec.get("column"), *spec.get("columns", [])]:
            if col and col not in contract["columns"]:
                raise ValueError(f"check '{name}': column '{col}' not in contract columns")
    return contract


def _validate_known_events(check_name: str, events: list) -> None:
    for e in events:
        try:
            date.fromisoformat(str(e["date"]))
            lo, hi = e["factor"]
            ok = bool(str(e["note"]).strip()) and 0 < lo <= hi
        except (KeyError, TypeError, ValueError):
            ok = False
        if not ok:
            raise ValueError(f"check '{check_name}': each known_event needs date (YYYY-MM-DD), a note, "
                             f"and factor [lo, hi] with 0 < lo <= hi (got {e!r})")
