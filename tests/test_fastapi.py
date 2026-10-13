"""HTTP-level tests for the FastAPI app. Skipped when fastapi/httpx are not installed
(they run in CI, which installs requirements-dev.txt)."""
import os
import unittest

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

from tests.helpers import Env


@unittest.skipUnless(HAVE_FASTAPI, "fastapi/httpx not installed")
class FastApiTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.env.seed_history(4)
        self.blocked = self.env.run(5, defects=["duplicates"])
        # point the app at the same database the Env created
        self._saved = {k: os.environ.get(k) for k in ("DATABASE_URL", "DQ_DB_PATH")}
        os.environ["DATABASE_URL"] = self.env.url or str(self.env.dir / "t.db")
        from api.app import app
        self.client = TestClient(app)

    def tearDown(self):
        for k, v in self._saved.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.env.close()

    def test_healthz_needs_no_database(self):
        self.assertEqual(self.client.get("/healthz").json(), {"ok": True})

    def test_health_reports_blocked(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body["status"], "blocked")
        self.assertEqual(body["pillars"]["correctness"], "fail")

    def test_runs_limit_is_validated_and_applied(self):
        self.assertEqual(len(self.client.get("/api/runs?limit=2").json()), 2)
        self.assertEqual(self.client.get("/api/runs?limit=0").status_code, 422)
        self.assertEqual(self.client.get("/api/runs?limit=999").status_code, 422)

    def test_run_detail_failures_and_404(self):
        rid = self.blocked.run_id
        detail = self.client.get(f"/api/runs/{rid}").json()
        self.assertEqual(detail["run"]["status"], "BLOCKED")
        fails = self.client.get(f"/api/runs/{rid}/failures", params={"check": "order_id_unique"}).json()
        self.assertGreater(len(fails), 0)
        self.assertEqual(self.client.get("/api/runs/nope").status_code, 404)

    def test_missing_database_is_a_503_not_a_crash(self):
        if self.env.url:
            self.skipTest("SQLite-only scenario")
        os.environ["DATABASE_URL"] = str(self.env.dir / "does-not-exist.db")
        self.assertEqual(self.client.get("/api/health").status_code, 503)


if __name__ == "__main__":
    unittest.main()
