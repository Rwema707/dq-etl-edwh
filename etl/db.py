"""Tiny database adapter so the same pipeline runs on SQLite (dev/tests) and PostgreSQL (prod).

Write SQL with `?` placeholders; the adapter rewrites them for Postgres. All reads return
list[dict]. Pick the backend with a URL or path:
    postgresql://user:pass@host/db   -> PostgreSQL (psycopg 3)
    anything else                    -> SQLite file path
Resolution order: explicit argument, then (read-only callers such as the API only) $API_DATABASE_URL,
then $DATABASE_URL, $DQ_DB_PATH, data/edwh.db. $API_DATABASE_URL should hold a read-only role
(see sql/readonly_role.sql) so the web tier never holds write credentials.
"""
from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
TABLES = ("dq_failed_rows", "dq_check_results", "dq_runs", "fact_orders")

# Columns added after the first release. Fresh databases get them from the schema files; existing
# databases get them here (idempotent), so `init_db` is always safe to run.
MIGRATIONS = [
    ("dq_runs", "dataset", "TEXT NOT NULL DEFAULT 'orders'"),
    ("fact_orders", "dataset", "TEXT NOT NULL DEFAULT 'orders'"),
]
# Indexes on migrated columns must be created after the migration, never in the schema script.
POST_MIGRATION_SQL = [
    "CREATE INDEX IF NOT EXISTS ix_dq_runs_dataset ON dq_runs(dataset, started_at)",
    "CREATE INDEX IF NOT EXISTS ix_fact_orders_dataset_batch ON fact_orders(dataset, batch_date)",
]


class Rollback(Exception):
    """Raise inside `with db.transaction()` to roll back without signalling a crash."""


class Database:
    def __init__(self, conn, dialect: str):
        self.conn, self.dialect = conn, dialect

    def _q(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def _args(self, params: Iterable):
        """psycopg needs None (not ()) for 'no parameters' so scripts and literal % stay legal;
        sqlite3 needs a sequence."""
        p = tuple(params)
        return (p or None) if self.dialect == "postgres" else p

    def execute(self, sql: str, params: Iterable = ()) -> None:
        self.conn.execute(self._q(sql), self._args(params))

    def executemany(self, sql: str, rows: Iterable[tuple]) -> None:
        if self.dialect == "postgres":
            with self.conn.cursor() as cur:
                cur.executemany(self._q(sql), list(rows))
        else:
            self.conn.executemany(sql, list(rows))

    def query(self, sql: str, params: Iterable = ()) -> list[dict]:
        cur = self.conn.execute(self._q(sql), self._args(params))
        return [dict(r) for r in cur.fetchall()]

    def one(self, sql: str, params: Iterable = ()) -> dict | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """All-or-nothing block. Commits on success, rolls back on any exception."""
        if self.dialect == "postgres":
            with self.conn.transaction():
                yield
            return
        self.conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def init_schema(self) -> None:
        text = (SQL_DIR / f"schema.{self.dialect}.sql").read_text()
        if self.dialect == "postgres":
            self.conn.execute(text)          # no params -> multi-statement script is allowed
        else:
            self.conn.executescript(text)
        self._migrate()

    def _migrate(self) -> None:
        for table, column, ddl in MIGRATIONS:
            if self.dialect == "postgres":
                self.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
            elif column not in [r["name"] for r in self.query(f"PRAGMA table_info({table})")]:
                self.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        for sql in POST_MIGRATION_SQL:
            self.execute(sql)

    def drop_all(self) -> None:
        """Used by tests only."""
        for t in TABLES:
            self.execute(f"DROP TABLE IF EXISTS {t}")

    def close(self) -> None:
        self.conn.close()


def is_postgres(target: str) -> bool:
    return target.startswith(("postgres://", "postgresql://"))


def resolve_target(target: str | None = None, readonly: bool = False) -> str:
    if target:
        return target
    if readonly and os.environ.get("API_DATABASE_URL"):
        return os.environ["API_DATABASE_URL"]
    return os.environ.get("DATABASE_URL") or os.environ.get("DQ_DB_PATH", "data/edwh.db")


def connect(target: str | None = None, readonly: bool = False) -> Database:
    target = resolve_target(target, readonly)
    if is_postgres(target):
        # imported lazily so SQLite-only use needs no driver
        import psycopg
        from psycopg.rows import dict_row
        # prepare_threshold=None: poolers such as Neon's PgBouncer do not support prepared statements.
        conn = psycopg.connect(target, autocommit=True, row_factory=dict_row, prepare_threshold=None)
        return Database(conn, "postgres")
    path = target.removeprefix("sqlite:///")
    if readonly:
        conn = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True, check_same_thread=False)
    else:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)  # autocommit
    conn.row_factory = sqlite3.Row
    return Database(conn, "sqlite")


def init_db(db: Database) -> None:
    db.init_schema()
