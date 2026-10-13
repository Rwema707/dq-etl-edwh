"""The dashboard's data layer: health states and pillar colours for each pipeline outcome."""
import unittest

from api import queries
from tests.helpers import Env


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


if __name__ == "__main__":
    unittest.main()
