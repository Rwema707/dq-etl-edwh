# Suggested next steps (in priority order)

Done so far: weekday-aware volume baseline with declared known events, "no run happened" watchdog, real-data
replay (Olist), cross-batch uniqueness, multi-dataset support (dataset column + picker), read-only API credentials.

1. **Per-dataset target tables** generated from the contract (today datasets share `fact_orders`'s shape).
2. **Authentication** on the dashboard/API (the read-only role limits damage but is not access control).
3. **Alert routing**: severity-based channels instead of one webhook.
4. **Rerun button** on the dashboard (e.g. calls the GitHub `workflow_dispatch` API through a protected endpoint,
   since the serverless API deliberately does not carry the ETL's dependencies).
5. **Bulk loading** (`COPY`) if batches grow beyond ~100k rows.
6. **Lockfile + `npm ci`** in CI once `dashboard/package-lock.json` is committed.
7. **Schema migrations framework** (e.g. Alembic) if the schema keeps evolving.
