# Suggested next steps (in priority order)

Done so far: weekday-aware volume baseline, "no run happened" watchdog, real-data replay (Olist), cross-batch
uniqueness, multi-dataset support (dataset column + dashboard picker).

1. **Per-dataset target tables** generated from the contract (today datasets share `fact_orders`'s shape).
2. **Read-only database role** for the API, and authentication on the dashboard.
3. **Alert routing**: severity-based channels instead of one webhook.
4. **Rerun button** on the dashboard (calls the same idempotent pipeline via a protected endpoint).
5. **Holiday/promotion calendar** for the volume check, so known spikes are expected rather than flagged.
6. **Bulk loading** (`COPY`) if batches grow beyond ~100k rows.
7. **Lockfile + `npm ci`** in CI once `dashboard/package-lock.json` is committed.
8. **Schema migrations framework** (e.g. Alembic) if the schema keeps evolving.
