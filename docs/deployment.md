# Deployment guide

Four services, all with free tiers (limits change, so check each pricing page before relying on them):

| Piece | Service | What it does |
|---|---|---|
| Code, CI, daily schedule | **GitHub** | Stores code, runs tests on every PR, runs the ETL daily |
| Database | **Neon** (or Supabase) | PostgreSQL holding `fact_orders` and the `dq_*` tables |
| API | **Render** | Runs `uvicorn api.app:app` |
| Dashboard | **Vercel** | Hosts the built React app |

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
1. neon.tech → new project → copy the **connection string** (looks like `postgresql://user:pass@ep-….neon.tech/neondb?sslmode=require`).
2. No manual SQL needed: every ETL run executes `sql/schema.postgres.sql` (idempotent `CREATE ... IF NOT EXISTS`).

## 3. Give GitHub the secrets
**Settings → Secrets and variables → Actions → New repository secret**
- `DATABASE_URL`: the Neon string (required)
- `SLACK_WEBHOOK_URL`: optional; a Slack Incoming Webhook URL for failure alerts

## 4. First run
**Actions → Daily ETL → Run workflow.** Leave the fields empty for a clean run; the job should go green.
Run it a few times with different dates (`2026-10-01`, `2026-10-02`, …) to build history: the row-count check
needs 3 earlier successful batches before it activates.

Demo a failure: run it with `inject = duplicates` (or `stale`, `null_customer`, `schema_drift`, …). The job turns
red, GitHub emails you, Slack pings if configured, and nothing is loaded. Run the same date again with `inject`
empty to repair it; reruns are idempotent.

After this the schedule (06:00 UTC daily, for the previous day's batch) takes over.

## 5. Deploy the API (Render)
1. render.com → **New → Blueprint** → select the repo (it reads `render.yaml`).
2. Set `DATABASE_URL` (same Neon string) and `CORS_ORIGINS` (fill in after step 6; for now `*` is fine for a demo).
3. Deploy. Check `https://<service>.onrender.com/healthz` and `/api/health`; `/docs` shows the interactive API docs.

Free instances sleep when idle, so the first request after a pause is slow. Open the URL before a demo.

## 6. Deploy the dashboard (Vercel)
1. vercel.com → **Add New → Project** → import the repo.
2. **Root Directory:** `dashboard`. Framework preset: Vite.
3. **Environment variable:** `VITE_API_BASE` = your Render URL (no trailing slash).
4. Deploy, then go back to Render and set `CORS_ORIGINS` to the Vercel URL.

## Local development
```bash
python -m simulator.seed_demo                       # SQLite demo data
uvicorn api.app:app --reload --port 8000            # API + /docs
cd dashboard && npm run dev                         # http://localhost:5173
```
To develop against Postgres, set `DATABASE_URL` in your shell and use the same commands.
The Postgres tests: `TEST_DATABASE_URL=postgresql://... pytest -q` (**this drops and recreates the tables in
that database; point it at a scratch database, never at production**).

## Troubleshooting
| Symptom | Likely cause |
|---|---|
| Dashboard says "Cannot reach the API" | `VITE_API_BASE` wrong or unset at build time (redeploy after changing it); API asleep |
| Browser console shows a CORS error | `CORS_ORIGINS` does not exactly match the dashboard URL (scheme, no trailing slash) |
| API returns 503 | `DATABASE_URL` missing/wrong on Render, or the ETL has never run |
| Workflow fails at "Check configuration" | `DATABASE_URL` secret not set |
| Row-count check shows SKIPPED | Fewer than 3 earlier successful batches; expected on a fresh database |
| Scheduled run did not fire | GitHub can delay schedules, and may pause them on repositories with no recent activity; trigger it manually |
| Neon connection errors after idle | Neon suspends idle databases; the first connection wakes it, retry the run |
