"""Runs every check in a contract and returns explicit results. Never raises on a bad check."""
from __future__ import annotations

from dataclasses import dataclass, field

from dq.checks import CHECKS, Context


@dataclass
class CheckResult:
    name: str
    type: str
    pillar: str
    severity: str
    status: str                       # PASS | FAIL | SKIPPED
    expected: str = ""
    actual: str = ""
    failed_rows: int = 0
    message: str = ""
    hint: str = ""
    failed_idx: list = field(default_factory=list, repr=False)

    @property
    def is_blocking_failure(self) -> bool:
        return self.status == "FAIL" and self.severity == "blocking"


def run_checks(contract: dict, ctx: Context) -> list[CheckResult]:
    results, schema_failed = [], False
    for spec in contract["checks"]:
        base = dict(name=spec["name"], type=spec["type"], pillar=spec["pillar"],
                    severity=spec["severity"], hint=spec.get("hint", ""))
        if schema_failed and spec["type"] != "schema":
            results.append(CheckResult(**base, status="SKIPPED", message="skipped: schema check failed"))
            continue
        try:
            o = CHECKS[spec["type"]](spec, ctx)
        except Exception as exc:  # a crashing check must be loud, never a silent pass
            results.append(CheckResult(**base, status="FAIL", message=f"check crashed: {type(exc).__name__}: {exc}"))
            continue
        status = "SKIPPED" if o.passed is None else ("PASS" if o.passed else "FAIL")
        results.append(CheckResult(**base, status=status, expected=o.expected, actual=o.actual,
                                   failed_rows=len(o.failed_idx), message=o.message, failed_idx=o.failed_idx))
        if spec["type"] == "schema" and status == "FAIL":
            schema_failed = True
    return results
