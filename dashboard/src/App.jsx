import { useCallback, useEffect, useMemo, useState } from "react";
import { getJSON } from "./api.js";
import { groupBatches } from "./format.js";
import StatusHeader from "./components/StatusHeader.jsx";
import BatchStrip from "./components/BatchStrip.jsx";
import BatchDetail from "./components/BatchDetail.jsx";

const REFRESH_MS = 30_000;

export default function App() {
  const [health, setHealth] = useState(null);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState(null);
  const [updated, setUpdated] = useState(null);
  const [pickedDate, setPickedDate] = useState(null);
  const [pickedRun, setPickedRun] = useState(null);

  const load = useCallback(async () => {
    try {
      const [h, r] = await Promise.all([getJSON("/api/health"), getJSON("/api/runs?limit=120")]);
      setHealth(h);
      setRuns(r);
      setError(null);
      setUpdated(new Date());
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const batches = useMemo(() => groupBatches(runs), [runs]);
  const active = batches.find((b) => b.date === pickedDate) ?? batches.at(-1) ?? null;
  const run = active?.attempts.find((a) => a.run_id === pickedRun) ?? active?.attempts[0] ?? null;

  const pickBatch = (date) => {
    setPickedDate(date);
    setPickedRun(null);
  };

  if (!health) {
    return (
      <main className="page">
        <h1 className="title">Orders data health</h1>
        {error ? (
          <div className="notice" role="alert">
            <p><strong>{error}.</strong></p>
            <p>
              Start the API with <code>python -m api.server --port 8000</code> and make sure the pipeline has run at
              least once (<code>python -m simulator.seed_demo</code> loads demo data).
            </p>
            <button className="btn" onClick={load}>Try again</button>
          </div>
        ) : (
          <p className="muted">Loading…</p>
        )}
      </main>
    );
  }

  return (
    <main className="page">
      <header className="masthead">
        <h1 className="title">Orders data health</h1>
        <div className="refresh">
          {error && <span className="stale">Update failed, showing earlier data. </span>}
          <span className="muted">
            Updated {updated?.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
          </span>
          <button className="btn" onClick={load}>Refresh</button>
        </div>
      </header>

      <StatusHeader health={health} />
      <BatchStrip batches={batches} activeDate={active?.date} onPick={pickBatch} />
      {active && run && (
        <BatchDetail batch={active} run={run} onPickRun={setPickedRun} />
      )}
    </main>
  );
}
