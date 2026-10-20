"""Check implementations. Each takes (spec, ctx) and returns an Outcome.

Rules of this module:
  * checks only OBSERVE; they never modify or "repair" data;
  * passed=None means "could not run" (reported as SKIPPED, never silently as a pass).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import statistics
from datetime import date, datetime

import pandas as pd


@dataclass
class Context:
    raw: pd.DataFrame                 # file contents exactly as delivered (strings)
    typed: pd.DataFrame               # same rows cast to contract types (bad values -> NaN/NaT, not fixed)
    columns: dict                     # contract columns {name: type}
    history: list[tuple[date, int]]   # (batch_date, source rows) of earlier successful batches, newest first
    as_of: datetime                   # reference "now" for freshness
    batch_date: date | None = None    # the batch being checked (needed for weekday-aware baselines)


@dataclass
class Outcome:
    passed: bool | None
    expected: str = ""
    actual: str = ""
    failed_idx: list = field(default_factory=list)
    message: str = ""


CHECKS: dict = {}


def check(type_name: str):
    def deco(fn):
        CHECKS[type_name] = fn
        return fn
    return deco


def _idx(mask: pd.Series) -> list:
    return mask[mask].index.tolist()


def _rows_outcome(mask: pd.Series, expected: str, what: str) -> Outcome:
    idx = _idx(mask)
    n = len(idx)
    pct = 100 * n / max(len(mask), 1)
    return Outcome(n == 0, expected, f"{n} rows ({pct:.2f}%)" if n else "0 rows",
                   idx, "" if n == 0 else f"{n} rows {what}")


@check("schema")
def schema(spec, ctx: Context) -> Outcome:
    exp, act = set(ctx.columns), set(ctx.raw.columns)
    missing, extra = sorted(exp - act), sorted(act - exp)
    if not missing and not extra:
        return Outcome(True, f"{len(exp)} contract columns", f"{len(act)} columns match")
    parts = []
    if missing:
        parts.append(f"missing {missing}")
    if extra:
        parts.append(f"unexpected {extra}")
    return Outcome(False, f"columns = {sorted(exp)}", "; ".join(parts), message="; ".join(parts))


@check("parseable")
def parseable(spec, ctx: Context) -> Outcome:
    mask = pd.Series(False, index=ctx.raw.index)
    per_col = {}
    for col, typ in ctx.columns.items():
        if typ == "string":
            continue
        m = ctx.raw[col].notna() & ctx.typed[col].isna()
        if m.any():
            per_col[col] = int(m.sum())
            mask |= m
    out = _rows_outcome(mask, "all values castable to contract types", "have unparseable values")
    if per_col:
        out.message += " (" + ", ".join(f"{c}: {n}" for c, n in per_col.items()) + ")"
    return out


@check("unique")
def unique(spec, ctx: Context) -> Outcome:
    s = ctx.raw[spec["column"]]
    mask = s.duplicated(keep=False) & s.notna()
    return _rows_outcome(mask, f"{spec['column']} unique", f"share a duplicated {spec['column']}")


@check("not_null")
def not_null(spec, ctx: Context) -> Outcome:
    cols = spec["columns"]
    mask = ctx.raw[cols].isna().any(axis=1)
    out = _rows_outcome(mask, f"no nulls in {cols}", "have a null required field")
    if not out.passed:
        counts = ctx.raw[cols].isna().sum()
        out.message += " (" + ", ".join(f"{c}: {int(n)}" for c, n in counts.items() if n) + ")"
    return out


@check("range")
def range_(spec, ctx: Context) -> Outcome:
    s, lo, hi = ctx.typed[spec["column"]], spec.get("min"), spec.get("max")
    bad = pd.Series(False, index=s.index)
    if lo is not None:
        bad |= s < lo
    if hi is not None:
        bad |= s > hi
    return _rows_outcome(bad & s.notna(), f"{spec['column']} in [{lo}, {hi}]", "are out of range")


@check("accepted_values")
def accepted_values(spec, ctx: Context) -> Outcome:
    s = ctx.raw[spec["column"]]
    mask = s.notna() & ~s.isin(spec["values"])
    out = _rows_outcome(mask, f"{spec['column']} in {spec['values']}", "have an unaccepted value")
    if not out.passed:
        out.message += " (e.g. " + ", ".join(f"{v} x{n}" for v, n in s[mask].value_counts().head(3).items()) + ")"
    return out


@check("regex")
def regex(spec, ctx: Context) -> Outcome:
    s = ctx.raw[spec["column"]]
    ok = s.fillna("").str.match(spec["pattern"])
    return _rows_outcome(s.notna() & ~ok, f"{spec['column']} matches {spec['pattern']}", "have a malformed value")


@check("row_count_band")
def row_count_band(spec, ctx: Context) -> Outcome:
    """Batch size must stay within +/- tolerance of the median of recent comparable batches.

    seasonality: weekday -> compare with the same weekday (Mondays with Mondays) once at least
    `min_history` such batches exist; until then, fall back to the last `window` batches of any day.
    The median (not the mean) keeps one freak day, such as a Black Friday spike, from skewing the baseline.
    """
    n = len(ctx.raw)
    if n == 0:
        return Outcome(False, "at least 1 row", "0 rows", message="empty batch")
    window, min_hist = spec.get("window", 7), spec.get("min_history", 3)
    hist, label = [rows for _, rows in ctx.history][:window], "recent"
    if spec.get("seasonality") == "weekday" and ctx.batch_date is not None:
        same = [rows for d, rows in ctx.history if d.weekday() == ctx.batch_date.weekday()][:window]
        if len(same) >= min_hist:
            hist, label = same, f"same-weekday ({ctx.batch_date:%A})"
    if len(hist) < min_hist:
        return Outcome(None, "needs history", f"{len(hist)} prior batches",
                       message=f"skipped: only {len(hist)} prior successful batches (need {min_hist})")
    base, tol = statistics.median(hist), spec["tolerance"]
    lo, hi = base * (1 - tol), base * (1 + tol)
    ok = lo <= n <= hi
    return Outcome(ok, f"{lo:,.0f} to {hi:,.0f} rows (median {base:,.0f} of last {len(hist)} {label} batches, +/-{tol:.0%})",
                   f"{n:,} rows",
                   message="" if ok else f"{n:,} rows is {(n - base) / base:+.0%} vs the {label} median of {base:,.0f}")


@check("freshness")
def freshness(spec, ctx: Context) -> Outcome:
    s = ctx.typed[spec["column"]].dropna()
    if s.empty:
        return Outcome(False, f"{spec['column']} present", "no valid timestamps", message="no valid timestamps")
    newest = s.max()
    lag_h = (pd.Timestamp(ctx.as_of) - newest).total_seconds() / 3600
    ok = lag_h <= spec["max_age_hours"]
    return Outcome(ok, f"newest {spec['column']} <= {spec['max_age_hours']}h old",
                   f"newest is {lag_h:.1f}h old ({newest:%Y-%m-%d %H:%M})",
                   message="" if ok else f"data is {lag_h:.1f}h old, SLA is {spec['max_age_hours']}h")
