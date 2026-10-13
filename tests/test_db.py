"""The database adapter: placeholder rewriting, backend selection and transaction behaviour."""
import tempfile
import unittest
from pathlib import Path

from etl.db import Database, Rollback, connect, is_postgres


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


if __name__ == "__main__":
    unittest.main()
