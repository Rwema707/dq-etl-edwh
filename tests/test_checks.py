"""Unit tests: one pass and one fail case per check type, plus engine and contract behaviour."""
import unittest
from datetime import date, datetime, timedelta

import pandas as pd

from dq.checks import CHECKS, Context
from dq.contract import load_contract
from dq.engine import run_checks
from etl.transform import transform
from tests.helpers import ROOT

COLS = {"order_id": "string", "amount": "float", "status": "string", "order_ts": "timestamp", "email": "string"}


BATCH = date(2026, 10, 7)   # a Wednesday


def ctx(rows, history=(), as_of="2026-10-02T06:00:00", batch_date=BATCH):
    """`history` may be plain ints (one earlier day each, newest first) or (date, rows) pairs."""
    raw = pd.DataFrame(rows, dtype=str)
    hist = [h if isinstance(h, tuple) else (batch_date - timedelta(days=i + 1), h) for i, h in enumerate(history)]
    return Context(raw, transform(raw, COLS), COLS, hist, datetime.fromisoformat(as_of), batch_date)


GOOD = [{"order_id": "A", "amount": "10.00", "status": "PAID", "order_ts": "2026-10-01T23:00:00", "email": "a@x.com"},
        {"order_id": "B", "amount": "20.00", "status": "SHIPPED", "order_ts": "2026-10-01T22:00:00", "email": "b@x.com"}]


def with_row(**kw):
    return GOOD + [{**GOOD[0], "order_id": "C", **kw}]


class CheckTests(unittest.TestCase):
    def test_schema(self):
        self.assertTrue(CHECKS["schema"]({}, ctx(GOOD)).passed)
        bad = pd.DataFrame(GOOD, dtype=str).rename(columns={"amount": "total"})
        c = Context(bad, bad, COLS, [], datetime.now())
        o = CHECKS["schema"]({}, c)
        self.assertFalse(o.passed)
        self.assertIn("missing ['amount']", o.message)

    def test_parseable(self):
        self.assertTrue(CHECKS["parseable"]({}, ctx(GOOD)).passed)
        o = CHECKS["parseable"]({}, ctx(with_row(amount="12,50", order_ts="yesterday")))
        self.assertFalse(o.passed)
        self.assertEqual(o.failed_idx, [2])

    def test_unique(self):
        spec = {"column": "order_id"}
        self.assertTrue(CHECKS["unique"](spec, ctx(GOOD)).passed)
        o = CHECKS["unique"](spec, ctx(GOOD + [GOOD[0]]))
        self.assertFalse(o.passed)
        self.assertEqual(len(o.failed_idx), 2)  # both copies are reported

    def test_not_null(self):
        spec = {"columns": ["order_id", "status"]}
        self.assertTrue(CHECKS["not_null"](spec, ctx(GOOD)).passed)
        o = CHECKS["not_null"](spec, ctx(GOOD + [{**GOOD[0], "order_id": "C", "status": None}]))
        self.assertFalse(o.passed)
        self.assertEqual(o.failed_idx, [2])

    def test_range(self):
        spec = {"column": "amount", "min": 0.01, "max": 100}
        self.assertTrue(CHECKS["range"](spec, ctx(GOOD)).passed)
        for bad in ("-5.00", "0", "100000"):
            self.assertFalse(CHECKS["range"](spec, ctx(with_row(amount=bad))).passed, bad)

    def test_accepted_values(self):
        spec = {"column": "status", "values": ["PAID", "SHIPPED"]}
        self.assertTrue(CHECKS["accepted_values"](spec, ctx(GOOD)).passed)
        self.assertFalse(CHECKS["accepted_values"](spec, ctx(with_row(status="REFUNDD"))).passed)

    def test_regex(self):
        spec = {"column": "email", "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"}
        self.assertTrue(CHECKS["regex"](spec, ctx(GOOD)).passed)
        self.assertFalse(CHECKS["regex"](spec, ctx(with_row(email="nope"))).passed)

    def test_row_count_band(self):
        spec = {"tolerance": 0.3, "window": 7, "min_history": 3}
        self.assertTrue(CHECKS["row_count_band"](spec, ctx(GOOD, history=[2, 2, 2])).passed)
        self.assertFalse(CHECKS["row_count_band"](spec, ctx(GOOD, history=[10, 10, 10])).passed)
        self.assertIsNone(CHECKS["row_count_band"](spec, ctx(GOOD, history=[2])).passed)   # skipped, not passed
        self.assertFalse(CHECKS["row_count_band"](spec, ctx([], history=[])).passed)       # empty batch always fails

    def test_row_count_uses_median_so_one_freak_day_cannot_skew_the_baseline(self):
        spec = {"tolerance": 0.3, "window": 7, "min_history": 3}
        # one 25x spike in history: the mean would be ~18, the median stays 4
        o = CHECKS["row_count_band"](spec, ctx(GOOD * 2, history=[4, 4, 4, 4, 4, 4, 100]))
        self.assertTrue(o.passed, o.message)

    def test_row_count_weekday_mode_compares_like_with_like(self):
        spec = {"tolerance": 0.3, "window": 4, "min_history": 3, "seasonality": "weekday"}
        wed = lambda w: (BATCH - timedelta(weeks=w), 100)          # earlier Wednesdays: 100 rows
        other = [(BATCH - timedelta(days=d), 20) for d in (1, 2, 3, 4)]  # other days are quiet: 20 rows
        history = sorted(other + [wed(1), wed(2), wed(3)], key=lambda x: x[0], reverse=True)
        rows = [GOOD[0]] * 100
        ok = CHECKS["row_count_band"](spec, ctx(rows, history=history))
        self.assertTrue(ok.passed, ok.message)                      # 100 vs same-weekday median 100
        self.assertIn("same-weekday", ok.expected)
        bad = CHECKS["row_count_band"](spec, ctx([GOOD[0]] * 20, history=history))
        self.assertFalse(bad.passed)                                # 20 vs 100 is a real drop for a Wednesday
        # the same 20 rows would look normal to a naive all-days baseline: that is the false alarm/miss weekday mode avoids
        naive = {**spec, "seasonality": None}
        self.assertTrue(CHECKS["row_count_band"](naive, ctx([GOOD[0]] * 20, history=other)).passed)

    def test_row_count_weekday_mode_falls_back_when_too_few_same_weekdays(self):
        spec = {"tolerance": 0.3, "window": 4, "min_history": 3, "seasonality": "weekday"}
        o = CHECKS["row_count_band"](spec, ctx(GOOD, history=[2, 2, 2]))   # consecutive days: only one is a Wednesday-match at most
        self.assertTrue(o.passed)
        self.assertIn("recent", o.expected)

    def test_freshness(self):
        spec = {"column": "order_ts", "max_age_hours": 24}
        self.assertTrue(CHECKS["freshness"](spec, ctx(GOOD)).passed)
        self.assertFalse(CHECKS["freshness"](spec, ctx(GOOD, as_of="2026-10-05T00:00:00")).passed)


class EngineTests(unittest.TestCase):
    def test_schema_failure_skips_rest_explicitly(self):
        contract = load_contract(ROOT / "contracts" / "orders.yaml")
        raw = pd.DataFrame(GOOD, dtype=str)[["order_id"]]
        results = run_checks(contract, Context(raw, raw, contract["columns"], [], datetime.now()))
        self.assertEqual(results[0].status, "FAIL")
        self.assertTrue(all(r.status == "SKIPPED" for r in results[1:]))

    def test_crashing_check_is_a_failure_not_a_pass(self):
        contract = {"checks": [{"name": "x", "type": "unique", "column": "nope", "pillar": "correctness",
                                "severity": "blocking"}]}
        r = run_checks(contract, ctx(GOOD))[0]
        self.assertEqual(r.status, "FAIL")
        self.assertIn("crashed", r.message)


class ContractTests(unittest.TestCase):
    def _write(self, text):
        import tempfile
        f = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
        f.write(text)
        f.close()
        return f.name

    def test_valid_contract_loads(self):
        self.assertEqual(load_contract(ROOT / "contracts" / "orders.yaml")["dataset"], "orders")

    def test_unknown_check_type_rejected(self):
        p = self._write("dataset: d\nsource: {}\ntarget: {}\ncolumns: {a: string}\n"
                        "checks: [{name: n, type: magic, pillar: correctness, severity: blocking}]\n")
        with self.assertRaisesRegex(ValueError, "unknown type"):
            load_contract(p)

    def test_bad_severity_rejected(self):
        p = self._write("dataset: d\nsource: {}\ntarget: {}\ncolumns: {a: string}\n"
                        "checks: [{name: n, type: unique, column: a, pillar: correctness, severity: meh}]\n")
        with self.assertRaisesRegex(ValueError, "severity"):
            load_contract(p)


if __name__ == "__main__":
    unittest.main()
