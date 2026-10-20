# Deployment guide

Three services, all with free tiers (limits change, so check each pricing page before relying on them):

| Piece | Service | What it does |
|---|---|---|
| Code, CI, daily schedule | **GitHub** | Stores code, runs tests on every PR, runs the ETL daily |
| Database | **Neon** (or Supabase) | PostgreSQL holding `fact_orders` and the `dq_*` tables |
| API **and** dashboard | **Vercel** | One project, two services (`vercel.json`): FastAPI on `/api/*`, React on `/` |

Do the steps in this order; each one produces a value the next needs.

## 1. Push the code to GitHub
```bash
git init && git add . && git commit -m "feat: data quality driven ETL"
git branch -M main
git remote add origin https://github.com/<you>/dq-etl-edwh.git
git push -u origin main
```
Then **Settings → Branches → Add rule** for `main`: require a pull request and one approval, and require the
`test` status check. From now on work on branches and open PRs.

Also run `cd dashboard && npm install` once and commit the generated `package-lock.json`.

## 2. Create the database (Neon)
1. neon.tech → new project → copy the **connection string** (`postgresql://user:pass@ep-….neon.tech/neondb?sslmode=require`).
   For Vercel, prefer the **pooled** connection string (host contains `-pooler`): serverless functions open many short connections.
2. No manual SQL needed: every ETL run executes `sql/schema.postgres.sql` (idempotent).

## 3. Give GitHub the secrets
**Settings → Secrets and variables → Actions → New repository secret**
- `DATABASE_URL`: the Neon string (required)
- `SLACK_WEBHOOK_URL`: optional; a Slack Incoming Webhook URL for failure alerts

## 4. First ETL run
**Actions → Daily ETL → Run workflow.** Leave the fields empty for a clean run; the job should go green.
Run it a few times with different dates (`2026-10-01`, `2026-10-02`, …) to build history: the row-count check
needs 3 earlier successful batches before it activates.

Demo a failure: run it with `inject = duplicates` (or `stale`, `null_customer`, `schema_drift`, …). The job turns
red, GitHub emails you, Slack pings if configured, and nothing is loaded. Run the same date again with `inject`
empty to repair it; reruns are idempotent. After this the schedule (06:00 UTC daily) takes over. A second workflow, **Pipeline watchdog**, runs at 09:30 UTC and
alerts (job fails, Slack pings) if no run has been recorded in the last 26 hours, i.e. when the schedule itself failed.

Want real data on the dashboard instead of simulated? See `docs/real-data.md` (workflow **Load Olist demo data**).

## 5. Deploy to Vercel (one project)
1. vercel.com → **Add New → Project** → import the repo. Leave **Root Directory** as the repository root.
2. In the project's **Build & Development Settings**, set **Framework Preset to "Services"**. Per Vercel's docs, a
   project only builds as services when that preset is selected *and* `vercel.json` has a `services` key.
3. **Environment Variables:** add `DATABASE_URL` (the same Neon string). Do **not** set `VITE_API_BASE`: the
   dashboard calls `/api/...` on its own origin, so no CORS setup is needed.
4. Deploy. Check:
   - `https://<project>.vercel.app/` → dashboard
   - `https://<project>.vercel.app/api/health` → JSON status
   - `https://<project>.vercel.app/api/docs` → interactive API docs

How `vercel.json` works: the `dq-api` service (repo root, entrypoint `api.app:app`) receives the original
request path, which is why the FastAPI routes themselves start with `/api`. The `dashboard` service builds the
Vite app. Rewrites are matched in order: `/api/(.*)` goes to the API, everything else to the dashboard.
`requirements.txt` is deliberately API-only (FastAPI + psycopg); pandas and PyYAML live in
`requirements-etl.txt` because only the ETL, tests and CI need them.

### Alternative: API on Render, dashboard elsewhere
`render.yaml` is kept for this case. Deploy the API there (`DATABASE_URL`, `CORS_ORIGINS` = the dashboard's exact
URL), then build the dashboard with `VITE_API_BASE=https://<service>.onrender.com`. Free Render instances sleep
when idle, so the first request after a pause is slow.

## Local development
```bash
python -m simulator.seed_demo                       # SQLite demo data
uvicorn api.app:app --reload --port 8000            # API + /api/docs
cd dashboard && npm run dev                         # http://localhost:5173
```
To develop against Postgres, set `DATABASE_URL` in your shell and use the same commands.
The Postgres tests: `TEST_DATABASE_URL=postgresql://... pytest -q` (**this drops and recreates the tables in
that database; point it at a scratch database, never at production**).

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Vercel builds only the dashboard (or one service) | Framework Preset is not "Services", or `vercel.json` is not at the repo root |
| Dashboard says "Cannot reach the API" | `/api/*` rewrite not applied (same cause as above); or `VITE_API_BASE` was set and points elsewhere |
| `/api/health` returns 503 | `DATABASE_URL` missing/wrong in Vercel, or the ETL has never run |
| Python service fails to start | Confirm the entrypoint `api.app:app` imports locally: `python -c "import api.app"` |
| Browser console shows a CORS error | Only when hosting API and dashboard on different origins: `CORS_ORIGINS` must match the dashboard URL exactly |
| Workflow fails at "Check configuration" | `DATABASE_URL` secret not set in GitHub |
| Row-count check shows SKIPPED | Fewer than 3 earlier successful batches; expected on a fresh database |
| Scheduled run did not fire | GitHub can delay schedules, and may pause them on repositories with no recent activity; trigger it manually |
| Neon connection errors after idle | Neon suspends idle databases; the first connection wakes it, retry the run |
