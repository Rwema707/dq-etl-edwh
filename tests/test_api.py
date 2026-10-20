"""The dashboard's data layer: health states and pillar colours for each pipeline outcome."""
import unittest

from api import queries
from dq.contract import load_contract
from etl.run import run_pipeline
from simulator.generate import generate_batch, write_batch
from tests.helpers import ROOT, Env


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()

    def tearDown(self):
        self.env.close()

    def test_empty_database_is_unknown_not_healthy(self):
        self.assertEqual(queries.get_health(self.env.db)["status"], "unknown")

    def test_healthy(self):
        self.env.seed_history(4)
        h = queries.get_health(self.env.db)
        self.assertEqual(h["status"], "healthy")
        self.assertEqual(set(h["pillars"].values()), {"pass"})

    def test_warning_is_degraded_with_warn_pillar(self):
        self.env.seed_history(4)
        self.env.run(5, defects=["bad_email"])
        h = queries.get_health(self.env.db)
        self.assertEqual(h["status"], "degraded")
        self.assertEqual(h["pillars"]["correctness"], "warn")

    def test_blocked_reports_failing_pillar_and_last_good_batch(self):
        self.env.seed_history(4)
        self.env.run(5, defects=["stale"])
        h = queries.get_health(self.env.db)
        self.assertEqual(h["status"], "blocked")
        self.assertEqual(h["pillars"]["freshness"], "fail")
        self.assertEqual(h["last_successful_batch"]["batch_date"], self.env.day(3).isoformat())

    def test_run_detail_and_failures(self):
        self.env.seed_history(4)
        s = self.env.run(5, defects=["duplicates"])
        detail = queries.get_run(self.env.db, s.run_id)
        self.assertEqual(detail["run"]["status"], "BLOCKED")
        self.assertTrue(any(c["status"] == "FAIL" and c["hint"] for c in detail["checks"]))
        self.assertGreater(len(queries.get_failures(self.env.db, s.run_id, "order_id_unique")), 0)
        self.assertIsNone(queries.get_run(self.env.db, "nope"))


class TwoDatasetTests(unittest.TestCase):
    """The simulated `orders` and a second dataset share one database; every view must stay separate."""

    def setUp(self):
        self.env = Env()
        self.env.seed_history(4)                                         # dataset "orders", 4 good runs
        other = load_contract(ROOT / "contracts" / "olist_orders.yaml")
        # a second dataset delivered to the same folder: Olist-shaped file with the columns its contract needs
        df = generate_batch(self.env.day(4), 50).drop(columns=["email"])
        df["status"] = "delivered"
        write_batch(df, self.env.dir, self.env.day(4))
        self.other = run_pipeline(self.env.db, other, self.env.day(4), str(self.env.dir))

    def tearDown(self):
        self.env.close()

    def test_datasets_are_listed_with_their_own_status_latest_first(self):
        ds = queries.list_datasets(self.env.db)
        self.assertEqual([d["dataset"] for d in ds], ["olist_orders", "orders"])
        self.assertEqual({d["dataset"]: d["runs"] for d in ds}, {"olist_orders": 1, "orders": 4})

    def test_default_view_is_the_most_recently_active_dataset(self):
        self.assertEqual(queries.get_health(self.env.db)["dataset"], "olist_orders")
        self.assertEqual(len(queries.list_runs(self.env.db)), 1)

    def test_explicit_dataset_filters_health_and_runs(self):
        h = queries.get_health(self.env.db, "orders")
        self.assertEqual((h["dataset"], h["status"]), ("orders", "healthy"))
        self.assertEqual(len(queries.list_runs(self.env.db, 30, "orders")), 4)
        self.assertEqual(queries.get_health(self.env.db, "nope")["status"], "unknown")

    def test_volume_history_is_not_mixed_between_datasets(self):
        from etl.run import _history
        d = self.env.day(5)
        self.assertEqual(len(_history(self.env.db, d, 30, "orders")), 4)
        self.assertEqual(len(_history(self.env.db, d, 30, "olist_orders")), 1)


if __name__ == "__main__":
    unittest.main()
