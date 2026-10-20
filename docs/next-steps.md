# Suggested next steps (in priority order)

Done since the first version: weekday-aware volume baseline, "no run happened" watchdog, real-data replay (Olist).

1. **Cross-batch uniqueness** check against `fact_orders` (the same order re-sent in a later batch).
2. **Dataset column on runs** so several datasets can share one database and one dashboard, with a dataset selector.
3. **Per-dataset target tables** (today the loader writes one fixed table shape).
4. **Read-only database role** for the API, and authentication on the dashboard.
5. **Alert routing**: severity-based channels instead of one webhook.
6. **Rerun button** on the dashboard (calls the same idempotent pipeline via a protected endpoint).
7. **Holiday/promotion calendar** for the volume check, so known spikes are expected rather than flagged.
8. **Bulk loading** (`COPY`) if batches grow beyond ~100k rows.
9. **Lockfile + `npm ci`** in CI once `dashboard/package-lock.json` is committed.
