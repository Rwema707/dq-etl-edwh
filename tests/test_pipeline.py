"""End-to-end tests: happy path, every failure path, idempotency and rollback."""
import json
import unittest

from etl.load import load
from etl.transform import transform
from simulator.generate import generate_batch, write_batch
from tests.helpers import D0, Env

# defect -> check that must catch it
BLOCKING_DEFECTS = {
    "duplicates": "order_id_unique",
    "null_customer": "required_fields_not_null",
    "negative_amount": "amount_in_range",
    "bad_status": "status_accepted",
    "bad_amount_text": "values_parseable",
    "stale": "freshness_within_sla",
    "volume_drop": "row_count_in_band",
    "schema_drift": "schema_matches_contract",
}


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def tearDown(self):
        self.env.close()

    def test_happy_path_loads_and_reconciles(self):
        s = self.env.run(0)
        self.assertEqual(s.status, "SUCCESS")
        self.assertEqual((s.source_rows, s.loaded_rows, s.blocking_failures), (300, 300, 0))
        self.assertEqual(self.env.count(0), 300)
        self.assertEqual(self.env.check_status(s.run_id, "source_equals_loaded"), "PASS")

    def test_each_blocking_defect_is_caught_and_nothing_is_loaded(self):
        self.env.seed_history(4)
        for defect, check in BLOCKING_DEFECTS.items():
            with self.subTest(defect=defect):
                s = self.env.run(5, defects=[defect])
                self.assertEqual(s.status, "BLOCKED")
                self.assertEqual(self.env.check_status(s.run_id, check), "FAIL")
                self.assertEqual(self.env.count(5), 0, "bad batch must not reach the target")
                self.assertGreater(s.blocking_failures, 0)

    def test_failed_rows_are_quarantined_for_diagnosis(self):
        self.env.seed_history(4)
        s = self.env.run(5, defects=["negative_amount"])
        n = self.env.db.one("SELECT COUNT(*) AS n FROM dq_failed_rows WHERE run_id=? AND check_name='amount_in_range'",
                            (s.run_id,))["n"]
        self.assertGreater(n, 0)

    def test_stored_failing_rows_are_strict_json_even_with_empty_cells(self):
        self.env.seed_history(4)
        s = self.env.run(5, defects=["null_customer"])
        rows = self.env.db.query("SELECT row_json FROM dq_failed_rows WHERE run_id=? AND check_name=?",
                                 (s.run_id, "required_fields_not_null"))
        parsed = [json.loads(r["row_json"], parse_constant=lambda c: self.fail(f"non-JSON constant {c}"))
                  for r in rows]
        self.assertTrue(parsed)
        self.assertTrue(all(p["customer_id"] is None for p in parsed))

    def test_warning_check_loads_but_is_flagged(self):
        self.env.seed_history(4)
        s = self.env.run(5, defects=["bad_email"])
        self.assertEqual(s.status, "SUCCESS")
        self.assertEqual(s.warnings, 1)
        self.assertEqual(self.env.check_status(s.run_id, "email_format"), "FAIL")
        self.assertEqual(self.env.count(5), 300)

    def test_schema_drift_skips_dependent_checks_loudly(self):
        s = self.env.run(0, defects=["schema_drift"])
        self.assertEqual(s.status, "BLOCKED")
        self.assertEqual(self.env.check_status(s.run_id, "order_id_unique"), "SKIPPED")

    def test_volume_check_is_skipped_not_passed_without_history(self):
        s = self.env.run(0)
        self.assertEqual(self.env.check_status(s.run_id, "row_count_in_band"), "SKIPPED")

    def test_missing_source_file_blocks_and_is_a_freshness_failure(self):
        s = self.env.run(0, write=False)
        self.assertEqual(s.status, "BLOCKED")
        self.assertEqual(self.env.check_status(s.run_id, "source_available"), "FAIL")

    def test_rerun_is_idempotent(self):
        self.env.run(0)
        self.env.run(0)
        self.assertEqual(self.env.count(0), 300)
        runs = self.env.db.one("SELECT COUNT(*) AS n FROM dq_runs")["n"]
        self.assertEqual(runs, 2)  # both runs are on record

    def test_blocked_rerun_leaves_previously_loaded_data_untouched(self):
        self.env.seed_history(4)
        self.assertEqual(self.env.run(5).status, "SUCCESS")
        self.assertEqual(self.env.run(5, defects=["duplicates"]).status, "BLOCKED")
        self.assertEqual(self.env.count(5), 300)

    def test_an_order_resent_in_a_later_batch_is_blocked(self):
        self.env.seed_history(2)
        old_ids = self.env.db.query("SELECT order_id FROM fact_orders WHERE batch_date = ? LIMIT 3",
                                    (self.env.day(0).isoformat(),))
        df = generate_batch(self.env.day(2), 300)
        df.loc[:2, "order_id"] = [r["order_id"] for r in old_ids]          # 3 orders from day 0, delivered again
        write_batch(df, self.env.dir, self.env.day(2))
        s = self.env.run(2, write=False)
        self.assertEqual(s.status, "BLOCKED")
        self.assertEqual(self.env.check_status(s.run_id, "order_id_not_loaded_before"), "FAIL")
        self.assertEqual(self.env.count(2), 0)

    def test_rerunning_the_same_batch_is_not_a_cross_batch_duplicate(self):
        self.env.run(0)
        s = self.env.run(0)                                                 # same ids, same batch
        self.assertEqual(s.status, "SUCCESS")
        self.assertEqual(self.env.check_status(s.run_id, "order_id_not_loaded_before"), "PASS")

    def test_unexpected_crash_is_recorded_as_error(self):
        self.env.db.execute("DROP TABLE fact_orders")  # simulate infrastructure failure (found by the lookup check)
        s = self.env.run(0)
        self.assertEqual(s.status, "ERROR")
        err = self.env.db.one("SELECT error FROM dq_runs WHERE run_id=?", (s.run_id,))["error"]
        self.assertIn("fact_orders", err)

    def test_reconciliation_failure_rolls_back(self):
        typed = transform(generate_batch(D0, 50), self.env.contract["columns"])
        loaded, ok = load(self.env.db, typed, "r1", D0, expected_rows=51)  # target will hold 50, not 51
        self.assertFalse(ok)
        self.assertEqual(self.env.count(0), 0)


if __name__ == "__main__":
    unittest.main()
