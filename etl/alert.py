"""Failure alerting. Alerts must never mask the real failure, so errors here are only logged."""
from __future__ import annotations

import json
import os
import urllib.request

from etl.log import log


def send_alert(text: str) -> None:
    log("ERROR", "alert", text=text)
    url = os.environ.get("SLACK_WEBHOOK_URL")
    if not url:
        return
    try:
        req = urllib.request.Request(url, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5)  # noqa: S310 - URL comes from trusted config
    except Exception as exc:
        log("WARNING", "alert_delivery_failed", error=str(exc))
