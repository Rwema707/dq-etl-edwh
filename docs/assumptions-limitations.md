# Assumptions and known limitations

**Assumptions**
- One source, one target table, daily batch; timestamps are UTC; run time is simulated as 06:00 UTC on the day after the batch (override with `--as-of`).
- Source data is simulated, with realistic volume and skew, so failures can be demonstrated on demand.
- "Blocking" rules halt the whole batch (all-or-nothing); partial loads are deliberately not supported.

**Limitations**
- Postgres here is a stand-in for a real EDWH (Snowflake/BigQuery/Redshift): the pipeline logic carries over, but the loader (`executemany`) is sized for tens of thousands of rows per batch; use `COPY`/bulk loaders beyond ~100k.
- The scheduled run generates its own simulated batch. A real deployment replaces `simulator.generate` with the real delivery (file drop, API pull) and keeps everything after it.
- The dashboard/API has no user authentication (data is simulated or public). The API can run on a read-only role (`sql/readonly_role.sql`, `API_DATABASE_URL`) that cannot write or read the warehouse table, which limits the damage of exposure but is not access control.
- The volume band uses the median of recent same-weekday batches and is skipped until 3 comparable batches exist. Holidays and promotions must be declared by hand under `known_events`; undeclared ones are flagged, by design.
- Datasets share one target table of fixed shape (`fact_orders`, with a `dataset` column). A dataset with different columns needs its own table and loader mapping.
- Cross-batch uniqueness only looks at the same dataset's loaded rows; the order_id primary key is still global, so two datasets reusing an id would surface as a load ERROR.
- Existing databases are upgraded automatically (`init_db` adds the `dataset` column, default `orders`), but there is no general migration framework.
- Failing-row storage is capped (100 per check) and email format is a basic pattern, not full RFC validation.
- No authentication on the dashboard/API (data is simulated; add auth before exposing real data).
- No automatic reruns or backfill orchestration; reruns are manual and idempotent.
- GitHub schedules can start late; there is no watchdog that alerts when no run happened at all.
