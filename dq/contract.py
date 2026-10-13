"""Load and validate a data contract. A bad contract fails at startup, not mid-run."""
from __future__ import annotations

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
        for col in [spec.get("column"), *spec.get("columns", [])]:
            if col and col not in contract["columns"]:
                raise ValueError(f"check '{name}': column '{col}' not in contract columns")
    return contract
