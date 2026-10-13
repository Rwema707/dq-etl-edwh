# Architecture

```mermaid
flowchart LR
  S[Source batch file<br/>orders_YYYY-MM-DD.csv] --> E[Extract<br/>read as delivered]
  E --> T[Cast to contract types<br/>no fixing]
  T --> Q{DQ engine<br/>contract.yaml}
  Q -- blocking failure --> B[BLOCK: no load<br/>quarantine failing rows<br/>alert + exit 1]
  Q -- pass / warnings only --> L[Load fact_orders<br/>single transaction]
  L --> R{Reconcile<br/>source = target?}
  R -- no --> RB[Rollback + BLOCK]
  R -- yes --> OK[SUCCESS]
  Q --> M[(dq_runs<br/>dq_check_results<br/>dq_failed_rows)]
  B --> M
  OK --> M
  M --> A[Read-only API<br/>FastAPI on Render] --> D[Dashboard<br/>React on Vercel]
  G[GitHub Actions<br/>daily 06:00 UTC] -.-> S
```

**Design decisions**
- *Gate before load.* Checks run on the in-memory batch; the target is untouched unless everything blocking passes.
- *Contract as configuration.* "Good data" lives in `contracts/orders.yaml`; reusing the pipeline for another dataset means a new contract and a new source/target mapping.
- *Observe, never repair.* Unparseable values become null for checking only; nothing is corrected or guessed.
- *Skipped is not passed.* A check that cannot run (no history, schema broken) is recorded as SKIPPED and shown as such.
- *Staging is in memory.* Raw rows for failing checks are persisted to `dq_failed_rows` (capped per check), which keeps the metadata DB small.

**Deployment shape.** GitHub Actions generates the day's simulated batch and runs the pipeline against Neon
Postgres. Render serves the read-only API from the same database; Vercel serves the static dashboard.
`etl/db.py` hides the SQLite/Postgres differences (placeholders, transactions, driver) behind one small class.
