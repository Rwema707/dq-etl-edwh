-- Read-only role for the web API (PostgreSQL). Least privilege: it can read the run-metadata tables the
-- dashboard needs and NOTHING else (not even fact_orders), and it cannot write.
--
-- 1. Replace CHANGE_ME_PASSWORD below (Neon/Supabase: run this in their SQL editor as the owner).
-- 2. Build the role's connection string (same host/database, user dq_reader, the new password).
-- 3. Put it in the API's environment as API_DATABASE_URL (Vercel). Keep DATABASE_URL (write access)
--    only where the ETL runs (GitHub Actions secret).
-- Safe to run repeatedly.

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dq_reader') THEN
    CREATE ROLE dq_reader LOGIN PASSWORD 'CHANGE_ME_PASSWORD';
  END IF;
END
$$;

-- Defence in depth: sessions of this role start read-only.
ALTER ROLE dq_reader SET default_transaction_read_only = on;

GRANT USAGE ON SCHEMA public TO dq_reader;
GRANT SELECT ON dq_runs, dq_check_results, dq_failed_rows TO dq_reader;
