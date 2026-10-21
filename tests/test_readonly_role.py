"""PostgreSQL only (runs in CI, skipped locally): sql/readonly_role.sql really gives least privilege.

Needs TEST_DATABASE_URL pointing at a scratch database where the user may create roles."""
import os
import unittest
from pathlib import Path

try:
    import psycopg
    from psycopg.conninfo import make_conninfo
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None

from tests.helpers import ROOT, Env

URL = os.environ.get("TEST_DATABASE_URL")
PASSWORD = "reader_test_pw"


@unittest.skipUnless(URL and psycopg, "needs TEST_DATABASE_URL and psycopg")
class ReadOnlyRoleTests(unittest.TestCase):
    def setUp(self):
        self.env = Env()
        self.env.seed_history(1)                              # a run in dq_runs and rows in fact_orders
        script = (Path(ROOT) / "sql" / "readonly_role.sql").read_text().replace("CHANGE_ME_PASSWORD", PASSWORD)
        self.env.db.conn.execute(script)
        self.reader = psycopg.connect(make_conninfo(URL, user="dq_reader", password=PASSWORD), autocommit=True)

    def tearDown(self):
        self.reader.close()
        self.env.db.drop_all()
        self.env.db.conn.execute("DROP OWNED BY dq_reader")
        self.env.db.conn.execute("DROP ROLE dq_reader")
        self.env.close()

    def test_can_read_what_the_dashboard_needs(self):
        for table in ("dq_runs", "dq_check_results", "dq_failed_rows"):
            self.reader.execute(f"SELECT COUNT(*) FROM {table}").fetchone()

    def test_cannot_write(self):
        with self.assertRaises(psycopg.Error):
            self.reader.execute("INSERT INTO dq_runs (run_id, batch_date, started_at, status) "
                                "VALUES ('x', '2026-01-01', 'now', 'SUCCESS')")
        with self.assertRaises(psycopg.Error):
            self.reader.execute("DELETE FROM dq_runs")

    def test_cannot_read_the_warehouse_table(self):
        with self.assertRaises(psycopg.Error):
            self.reader.execute("SELECT * FROM fact_orders").fetchone()

    def test_the_api_queries_work_with_these_credentials(self):
        from api import queries
        from etl.db import Database
        db = Database(psycopg.connect(make_conninfo(URL, user="dq_reader", password=PASSWORD),
                                      autocommit=True, row_factory=dict_row), "postgres")
        try:
            self.assertEqual(queries.get_health(db)["status"], "healthy")
            self.assertEqual(len(queries.list_runs(db)), 1)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
