"""Real-data path: Olist-shaped source files -> daily batches -> contract checks -> warehouse."""
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from dq.contract import load_contract
from etl.backfill import backfill
from etl.run import run_pipeline
from etl.watchdog import check_recent_run
from sources.fetch_olist import count_rows, verify
from sources.olist import build_orders, write_daily_batches
from tests.helpers import ROOT, Env

FIX = Path(__file__).resolve().parent / "fixtures" / "olist"
D1, D2 = date(2018, 3, 5), date(2018, 3, 6)
REPEAT_BUYER_ORDERS = ("b81ef226f3fe1789b1e8b2acac839d17", "a9810da82917af2d9aefd1278f1dcfa0")
TWO_PAYMENTS = "683bf306149bb869980b68d48a1bd6ab"


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.df = build_orders(FIX).set_index("order_id")

    def test_all_orders_are_kept_and_columns_match_the_contract(self):
        self.assertEqual(len(self.df), 12)
        self.assertEqual(list(self.df.columns), ["customer_id", "amount", "status", "order_ts"])
        self.assertEqual(list(load_contract(ROOT / "contracts" / "olist_orders.yaml")["columns"]),
                         ["order_id", "customer_id", "amount", "status", "order_ts"])

    def test_amount_is_the_sum_of_an_orders_payments(self):
        self.assertEqual(self.df.loc[TWO_PAYMENTS, "amount"], "38.58")          # 30.00 voucher + 8.58 card
        self.assertEqual(self.df.loc["b81ef226f3fe1789b1e8b2acac839d17", "amount"], "99.33")

    def test_source_defects_are_not_hidden(self):
        no_payment = self.df[self.df["status"] == "created"].iloc[0]
        self.assertTrue(pd.isna(no_payment["amount"]))   # stays empty so the quality checks can see it

    def test_timestamp_is_iso_and_customer_is_the_real_person(self):
        self.assertEqual(self.df.loc[TWO_PAYMENTS, "order_ts"], "2018-03-06T20:10:11")
        self.assertEqual(self.df.loc[REPEAT_BUYER_ORDERS[0], "customer_id"],
                         self.df.loc[REPEAT_BUYER_ORDERS[1], "customer_id"])

    def test_one_batch_file_per_purchase_date_and_range_filter(self):
        with tempfile.TemporaryDirectory() as tmp:
            days = write_daily_batches(build_orders(FIX), tmp)
            self.assertEqual(days, [D1, D2])
            self.assertEqual(len(pd.read_csv(Path(tmp) / "orders_2018-03-05.csv")), 7)
            self.assertEqual(write_daily_batches(build_orders(FIX), tmp, start=D2), [D2])


class PipelineOnRealShapedDataTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.contract = load_contract(ROOT / "contracts" / "olist_orders.yaml")
        write_daily_batches(build_orders(FIX), self.env.dir)

    def tearDown(self):
        self.env.close()

    def run_day(self, d):
        return run_pipeline(self.env.db, self.contract, d, str(self.env.dir))

    def test_clean_day_loads_even_though_olist_has_no_email_column(self):
        s = self.run_day(D1)
        self.assertEqual((s.status, s.loaded_rows), ("SUCCESS", 7))
        row = self.env.db.one("SELECT email, customer_id FROM fact_orders WHERE order_id = ?",
                              ("b81ef226f3fe1789b1e8b2acac839d17",))
        self.assertIsNone(row["email"])

    def test_order_without_a_payment_blocks_its_day_and_is_quarantined(self):
        s = self.run_day(D2)
        self.assertEqual(s.status, "BLOCKED")
        self.assertEqual(self.env.check_status(s.run_id, "required_fields_not_null"), "FAIL")
        n = self.env.db.one("SELECT COUNT(*) AS n FROM dq_failed_rows WHERE run_id=? AND check_name='required_fields_not_null'",
                            (s.run_id,))["n"]
        self.assertEqual(n, 1)
        self.assertEqual(self.env.db.one("SELECT COUNT(*) AS n FROM fact_orders WHERE batch_date='2018-03-06'")["n"], 0)

    def test_backfill_runs_oldest_first_and_skips_days_without_a_delivery(self):
        res = backfill(self.env.db, self.contract, date(2018, 3, 4), date(2018, 3, 7), str(self.env.dir))
        self.assertEqual([(d.day, None if s is None else s.status) for d, s in res],
                         [(4, None), (5, "SUCCESS"), (6, "BLOCKED"), (7, None)])

    def test_backfill_can_record_missing_days_as_blocked(self):
        res = backfill(self.env.db, self.contract, date(2018, 3, 4), date(2018, 3, 5), str(self.env.dir),
                       skip_missing=False)
        self.assertEqual([s.status for _, s in res], ["BLOCKED", "SUCCESS"])
        self.assertEqual(self.env.check_status(res[0][1].run_id, "source_available"), "FAIL")


class FetchVerificationTests(unittest.TestCase):
    def test_row_count_ignores_the_header_and_handles_quoted_fields(self):
        self.assertEqual(count_rows(FIX / "olist_order_payments_dataset.csv"), 12)   # 11 orders, one pays twice

    def test_wrong_row_count_is_rejected(self):
        verify(FIX / "olist_order_payments_dataset.csv", 12)
        with self.assertRaisesRegex(ValueError, "expected 99,441 rows, found 12"):
            verify(FIX / "olist_orders_dataset.csv", 99_441)


class WatchdogTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def tearDown(self):
        self.env.close()

    def test_no_runs_is_stale(self):
        ok, msg = check_recent_run(self.env.db, datetime.now(timezone.utc), 26)
        self.assertFalse(ok)
        self.assertIn("ever been recorded", msg)

    def test_recent_run_is_ok_and_old_run_is_stale(self):
        self.env.run(0)
        now = datetime.now(timezone.utc)
        self.assertTrue(check_recent_run(self.env.db, now, 26)[0])
        ok, msg = check_recent_run(self.env.db, now + timedelta(hours=40), 26)
        self.assertFalse(ok)
        self.assertIn("limit is 26h", msg)

    def test_watchdog_can_be_scoped_to_a_dataset(self):
        self.env.run(0)                                               # a run of dataset "orders" only
        now = datetime.now(timezone.utc)
        self.assertTrue(check_recent_run(self.env.db, now, 26, "orders")[0])
        ok, msg = check_recent_run(self.env.db, now, 26, "olist_orders")
        self.assertFalse(ok)
        self.assertIn("olist_orders", msg)


if __name__ == "__main__":
    unittest.main()
