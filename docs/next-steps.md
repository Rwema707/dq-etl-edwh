# Suggested next steps (in priority order)

1. **Smarter volume baseline**: compare to the same weekday, or use median/MAD instead of mean +/- %.
2. **"No run happened" watchdog**: alert when no run is recorded for a day (GitHub schedules can be missed).
3. **Cross-batch uniqueness** check against `fact_orders`.
4. **Read-only database role** for the API, and authentication on the dashboard.
5. **Alert routing**: severity-based channels instead of one webhook.
6. **Rerun button** on the dashboard (calls the same idempotent pipeline via a protected endpoint).
7. **Bulk loading** (`COPY`) if batches grow beyond ~100k rows.
8. **Second dataset** by copying the contract: validates the "reusable template" claim.
9. **Lockfile + `npm ci`** in CI once `dashboard/package-lock.json` is committed.
