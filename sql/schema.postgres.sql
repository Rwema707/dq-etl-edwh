-- PostgreSQL schema (Neon / Supabase / any Postgres 13+). Safe to run repeatedly.
CREATE TABLE IF NOT EXISTS fact_orders (
  order_id    TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL,
  email       TEXT,
  amount      NUMERIC(12,2) NOT NULL,
  status      TEXT NOT NULL,
  order_ts    TIMESTAMP NOT NULL,
  batch_date  DATE NOT NULL,
  run_id      TEXT NOT NULL,
  loaded_at   TIMESTAMPTZ NOT NULL,
  dataset     TEXT NOT NULL DEFAULT 'orders'
);
CREATE INDEX IF NOT EXISTS ix_fact_orders_batch ON fact_orders(batch_date);

CREATE TABLE IF NOT EXISTS dq_runs (
  run_id TEXT PRIMARY KEY,
  batch_date TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  source_rows INTEGER,
  loaded_rows INTEGER,
  blocking_failures INTEGER DEFAULT 0,
  warnings INTEGER DEFAULT 0,
  error TEXT,
  dataset TEXT NOT NULL DEFAULT 'orders'
);
CREATE INDEX IF NOT EXISTS ix_dq_runs_started ON dq_runs(started_at);
CREATE TABLE IF NOT EXISTS dq_check_results (
  run_id TEXT NOT NULL,
  position INTEGER NOT NULL,
  check_name TEXT NOT NULL,
  check_type TEXT NOT NULL,
  pillar TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT NOT NULL,
  expected TEXT,
  actual TEXT,
  failed_rows INTEGER DEFAULT 0,
  message TEXT,
  hint TEXT
);
CREATE INDEX IF NOT EXISTS ix_dq_checks_run ON dq_check_results(run_id);
CREATE TABLE IF NOT EXISTS dq_failed_rows (
  run_id TEXT NOT NULL,
  check_name TEXT NOT NULL,
  csv_line INTEGER,
  row_json TEXT
);
CREATE INDEX IF NOT EXISTS ix_dq_failed_run ON dq_failed_rows(run_id, check_name);
