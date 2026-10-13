# Data Quality–Driven ETL for an EDWH

One source dataset (`orders`) → one warehouse table (`fact_orders`), with data quality enforced
**before** anything is loaded. Bad data is blocked, quarantined for diagnosis, reported loudly, and
never silently fixed. A dashboard lets a non-engineer see data health without reading code.

## What it does
1. **Extract** the day's batch file exactly as delivered.
2. **Check** it against a data contract (`contracts/orders.yaml`): correctness, completeness, freshness.
3. **Block or load.** Any blocking failure → nothing is loaded, failing rows are stored, an alert fires,
   exit code is non-zero. Otherwise the batch is loaded in one transaction and reconciled against the source.
4. **Record** every run, check result and failing row in metadata tables, shown on the dashboard.

## Quick start (Python 3.11+)
```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env

python -m simulator.seed_demo          # builds ~11 demo runs, including failures (SQLite by default)
uvicorn api.app:app --port 8000        # FastAPI on :8000, docs at /docs (serves dashboard/dist if built)
python -m unittest discover -s tests -t .   # or: pytest -q
```

### Dashboard (React + Vite, needs Node 20+)
```bash
cd dashboard
npm install
npm run dev        # http://localhost:5173, proxies /api to the Python API on :8000
npm run build      # outputs dashboard/dist; then http://localhost:8000 serves it
```
Without a build, the API serves `dashboard/legacy.html` (zero-build version).
`python -m api.server` is a dependency-free fallback API if FastAPI is not installed.
For a separately hosted frontend, set `VITE_API_BASE=https://your-api-host` before `npm run build`.

## Database and deployment
Set `DATABASE_URL=postgresql://...` to use PostgreSQL; otherwise a local SQLite file is used. The same
code and tests run on both. A daily GitHub Actions workflow runs the ETL; the API deploys to Render and the
dashboard to Vercel. Step-by-step: [`docs/deployment.md`](docs/deployment.md).

## Run it yourself
```bash
python -m simulator.generate --date 2026-10-08                      # clean batch
python -m simulator.generate --date 2026-10-09 --inject duplicates  # defective batch
python -m etl.run --date 2026-10-08     # exit 0 = loaded
python -m etl.run --date 2026-10-09     # exit 1 = BLOCKED, nothing loaded
```
Defects you can inject: `duplicates, null_customer, negative_amount, bad_status, bad_amount_text,
bad_email, stale, volume_drop, schema_drift`.

## How to rerun and debug a failed batch
1. Open the dashboard; the banner says what failed and what data the warehouse still holds.
2. Click the failing run. Each failed check shows expected vs actual and a **First step** hint.
3. Use the failing-rows table (CSV line numbers + the row as delivered) to take evidence to the source owner.
4. When the upstream file is corrected, rerun the same date: `python -m etl.run --date YYYY-MM-DD`.
   Reruns are idempotent (the batch's rows are replaced atomically), and every attempt stays on record.
5. Exit codes: `0` loaded, `1` blocked by data quality, `2` unexpected error. Logs are JSON lines
   (stderr and `LOG_FILE`).

## Layout
`contracts/` data contract · `dq/` check engine · `etl/` pipeline · `simulator/` data + defect injector ·
`api/` read-only API (FastAPI) · `dashboard/` React UI (`src/`) + legacy single file · `sql/` DDL · `tests/` · `docs/`

See `docs/` for architecture, the DQ checklist, assumptions/limitations and next steps.
