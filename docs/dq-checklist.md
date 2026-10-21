# Data quality checklist (`orders`)

| # | Check | Pillar | Severity | Rule | Catches |
|---|---|---|---|---|---|
| 1 | schema_matches_contract | Correctness | Blocking | Columns exactly match contract | Upstream layout change |
| 2 | values_parseable | Correctness | Blocking | amount is numeric, order_ts is ISO-8601 | Bad formats (`12,50`) |
| 3 | order_id_unique | Correctness | Blocking | No duplicated order_id | Re-sent records |
| 3b | order_id_not_loaded_before | Correctness | Blocking | No order_id already loaded by an **earlier batch** of the same dataset (rerunning the same batch is fine) | Old records re-sent in a later delivery |
| 4 | amount_in_range | Correctness | Blocking | 0.01 ≤ amount ≤ 10,000 | Negative/zero/absurd amounts |
| 5 | status_accepted | Correctness | Blocking | status in 5 known values | Typos, unannounced new statuses |
| 6 | email_format | Correctness | **Warning** | Matches a basic email pattern | Malformed emails (not used for joins) |
| 7 | required_fields_not_null | Completeness | Blocking | order_id, customer_id, amount, status, order_ts non-null | Broken upstream joins |
| 8 | row_count_in_band | Completeness | Blocking | Within ±30% of the median of the last 4 **same-weekday** batches (falls back to the last 4 batches of any day until 3 same-weekday batches exist; needs ≥3 batches). Contracts can declare `known_events` (e.g. Black Friday) whose date uses an expected multiple of the baseline instead | Partial extracts, outages |
| 9 | freshness_within_sla | Freshness | Blocking | Newest order_ts ≤ 24h old at run time | Stale or re-delivered data |
| 10 | source_equals_loaded | Completeness | Blocking | Rows in target = rows in source after load | Load bugs; triggers rollback |
| – | source_available | Freshness | Blocking | Batch file exists | Missing delivery |

Each rule has at least one failing-case test (`tests/test_checks.py`, `tests/test_pipeline.py`).

The Olist (real data) contract, `contracts/olist_orders.yaml`, applies the same pillars with 9 checks and no email rule.
