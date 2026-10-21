"""The database adapter: placeholder rewriting, backend selection and transaction behaviour."""
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

from etl.db import Database, Rollback, connect, init_db, is_postgres, resolve_target


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params))


class AdapterTests(unittest.TestCase):
    def test_postgres_placeholders_are_rewritten(self):
        c = FakeConn()
        Database(c, "postgres").execute("DELETE FROM t WHERE a = ? AND b = ?", (1, 2))
        self.assertEqual(c.calls, [("DELETE FROM t WHERE a = %s AND b = %s", (1, 2))])

    def test_sqlite_placeholders_are_untouched(self):
        c = FakeConn()
        Database(c, "sqlite").execute("DELETE FROM t WHERE a = ?", (1,))
        self.assertEqual(c.calls, [("DELETE FROM t WHERE a = ?", (1,))])

    def test_sqlite_gets_an_empty_tuple_when_there_are_no_params(self):
        c = FakeConn()
        Database(c, "sqlite").execute("SELECT 1")
        self.assertEqual(c.calls[0][1], ())

    def test_no_params_is_sent_as_none_so_scripts_and_percent_signs_are_safe(self):
        c = FakeConn()
        Database(c, "postgres").execute("SELECT 1")
        self.assertEqual(c.calls[0][1], None)

    def test_backend_is_chosen_from_the_url(self):
        self.assertTrue(is_postgres("postgresql://u:p@h/db?sslmode=require"))
        self.assertTrue(is_postgres("postgres://u:p@h/db"))
        self.assertFalse(is_postgres("data/edwh.db"))
        self.assertFalse(is_postgres("sqlite:///data/edwh.db"))

    def test_every_table_exists_in_both_schemas(self):
        from etl.db import SQL_DIR, TABLES
        for dialect in ("sqlite", "postgres"):
            text = (SQL_DIR / f"schema.{dialect}.sql").read_text()
            for t in TABLES:
                self.assertIn(f"CREATE TABLE IF NOT EXISTS {t} ", text, f"{t} missing in {dialect}")


class ResolveTargetTests(unittest.TestCase):
    ENV = {"API_DATABASE_URL": "postgresql://reader@h/db", "DATABASE_URL": "postgresql://owner@h/db",
           "DQ_DB_PATH": "local.db"}

    def test_explicit_target_always_wins(self):
        with mock.patch.dict("os.environ", self.ENV, clear=True):
            self.assertEqual(resolve_target("x.db", readonly=True), "x.db")

    def test_read_only_callers_prefer_the_api_credentials(self):
        with mock.patch.dict("os.environ", self.ENV, clear=True):
            self.assertEqual(resolve_target(readonly=True), "postgresql://reader@h/db")

    def test_the_etl_never_uses_the_read_only_credentials(self):
        with mock.patch.dict("os.environ", self.ENV, clear=True):
            self.assertEqual(resolve_target(), "postgresql://owner@h/db")

    def test_falls_back_to_database_url_then_local_file(self):
        with mock.patch.dict("os.environ", {"DATABASE_URL": "postgresql://owner@h/db"}, clear=True):
            self.assertEqual(resolve_target(readonly=True), "postgresql://owner@h/db")
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual(resolve_target(readonly=True), "data/edwh.db")


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = connect(str(Path(self.tmp.name) / "t.db"))
        self.db.execute("CREATE TABLE t (a INTEGER)")

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def count(self):
        return self.db.one("SELECT COUNT(*) AS n FROM t")["n"]

    def test_commits_on_success(self):
        with self.db.transaction():
            self.db.execute("INSERT INTO t VALUES (?)", (1,))
        self.assertEqual(self.count(), 1)

    def test_rolls_back_on_exception(self):
        with self.assertRaises(ValueError), self.db.transaction():
            self.db.execute("INSERT INTO t VALUES (?)", (1,))
            raise ValueError("boom")
        self.assertEqual(self.count(), 0)

    def test_rollback_signal_rolls_back(self):
        with self.assertRaises(Rollback), self.db.transaction():
            self.db.execute("INSERT INTO t VALUES (?)", (1,))
            raise Rollback
        self.assertEqual(self.count(), 0)

    def test_query_returns_plain_dicts(self):
        self.db.execute("INSERT INTO t VALUES (?)", (7,))
        self.assertEqual(self.db.query("SELECT a FROM t"), [{"a": 7}])


OLD_SCHEMA = """
CREATE TABLE dq_runs (run_id TEXT PRIMARY KEY, batch_date TEXT NOT NULL, started_at TEXT NOT NULL,
  finished_at TEXT, status TEXT NOT NULL, source_rows INTEGER, loaded_rows INTEGER,
  blocking_failures INTEGER DEFAULT 0, warnings INTEGER DEFAULT 0, error TEXT);
CREATE TABLE fact_orders (order_id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, email TEXT, amount REAL NOT NULL,
  status TEXT NOT NULL, order_ts TEXT NOT NULL, batch_date TEXT NOT NULL, run_id TEXT NOT NULL, loaded_at TEXT NOT NULL);
INSERT INTO dq_runs (run_id, batch_date, started_at, status) VALUES ('old1', '2026-10-01', '2026-10-02T06:00:00', 'SUCCESS');
INSERT INTO fact_orders VALUES ('o1', 'c1', NULL, 5.0, 'PAID', '2026-10-01T10:00:00', '2026-10-01', 'old1', '2026-10-02T06:00:00');
"""


class MigrationTests(unittest.TestCase):
    def test_database_created_before_the_dataset_column_is_upgraded_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = connect(str(Path(tmp) / "old.db"))
            db.conn.executescript(OLD_SCHEMA)
            init_db(db)                                   # must not fail, must keep the data
            self.assertEqual(db.one("SELECT dataset FROM dq_runs WHERE run_id='old1'")["dataset"], "orders")
            self.assertEqual(db.one("SELECT dataset FROM fact_orders WHERE order_id='o1'")["dataset"], "orders")
            init_db(db)                                   # and be safe to run again
            db.close()


class DatasetIsolationTests(unittest.TestCase):
    def test_reloading_one_dataset_never_deletes_another_datasets_rows(self):
        from etl.load import load
        from etl.transform import transform
        from simulator.generate import generate_batch
        from tests.helpers import Env
        env = Env()
        try:
            cols = env.contract["columns"]
            a = transform(generate_batch(date(2026, 10, 1), 20), cols)
            b = transform(generate_batch(date(2026, 10, 1), 20), cols)
            b["order_id"] = "B-" + b["order_id"]          # distinct ids, SAME batch date
            load(env.db, a, "ra", date(2026, 10, 1), dataset="alpha")
            load(env.db, b, "rb", date(2026, 10, 1), dataset="beta")
            load(env.db, b, "rb2", date(2026, 10, 1), dataset="beta")        # rerun beta
            def n(d):
                return env.db.one("SELECT COUNT(*) AS n FROM fact_orders WHERE dataset = ?", (d,))["n"]

            self.assertEqual((n("alpha"), n("beta")), (20, 20))
        finally:
            env.close()


if __name__ == "__main__":
    unittest.main()
