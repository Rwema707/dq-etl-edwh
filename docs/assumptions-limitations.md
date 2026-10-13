# Assumptions and known limitations

**Assumptions**
- One source, one target table, daily batch; timestamps are UTC; run time is simulated as 06:00 UTC on the day after the batch (override with `--as-of`).
- Source data is simulated, with realistic volume and skew, so failures can be demonstrated on demand.
- "Blocking" rules halt the whole batch (all-or-nothing); partial loads are deliberately not supported.

**Limitations**
- Postgres here is a stand-in for a real EDWH (Snowflake/BigQuery/Redshift): the pipeline logic carries over, but the loader (`executemany`) is sized for tens of thousands of rows per batch; use `COPY`/bulk loaders beyond ~100k.
- The scheduled run generates its own simulated batch. A real deployment replaces `simulator.generate` with the real delivery (file drop, API pull) and keeps everything after it.
- The API connects with the same credentials as the ETL. It only issues SELECTs, but production should give it a read-only database role.
- The volume band is a simple trailing average and ignores weekly seasonality (weekends ~28% lower); it can false-alarm on unusual days and is skipped for the first 3 batches.
- Uniqueness is checked within a batch only, not against rows already in the target (a cross-batch duplicate surfaces as a load ERROR).
- Failing-row storage is capped (100 per check) and email format is a basic pattern, not full RFC validation.
- No authentication on the dashboard/API (data is simulated; add auth before exposing real data).
- No automatic reruns or backfill orchestration; reruns are manual and idempotent.
- GitHub schedules can start late; there is no watchdog that alerts when no run happened at all.
