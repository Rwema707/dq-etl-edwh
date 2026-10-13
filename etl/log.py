"""Structured JSON logging: one event per line, to stderr and (optionally) a file."""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def log(level: str, event: str, **fields) -> None:
    line = json.dumps({"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       "level": level, "event": event, **fields}, default=str)
    print(line, file=sys.stderr)
    path = os.environ.get("LOG_FILE")
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
