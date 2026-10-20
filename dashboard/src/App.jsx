import { useCallback, useEffect, useMemo, useState } from "react";
import { getJSON } from "./api.js";
import { cap, groupBatches, words } from "./format.js";
import StatusHeader from "./components/StatusHeader.jsx";
import BatchStrip from "./components/BatchStrip.jsx";
import BatchDetail from "./components/BatchDetail.jsx";

const REFRESH_MS = 30_000;
const fromUrl = () => new URLSearchParams(window.location.search).get("dataset");

export default function App() {
  const [dataset, setDataset] = useState(fromUrl);        // null = whichever dataset ran most recently
  const [datasets, setDatasets] = useState([]);
  const [health, setHealth] = useState(null);
  const [runs, setRuns] = useState([]);
  const [error, setError] = useState(null);
  const [updated, setUpdated] = useState(null);
  const [pickedDate, setPickedDate] = useState(null);
  const [pickedRun, setPickedRun] = useState(null);

  const load = useCallback(async () => {
    const q = dataset ? `dataset=${encodeURIComponent(dataset)}` : "";
    try {
      const [h, r, d] = await Promise.all([
        getJSON(`/api/health?${q}`),
        getJSON(`/api/runs?limit=120&${q}`),
        getJSON("/api/datasets"),
      ]);
      setHealth(h);
      setRuns(r);
      setDatasets(d);
      setError(null);
      setUpdated(new Date());
    } catch (e) {
      setError(e.message);
    }
  }, [dataset]);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const current = dataset ?? health?.dataset ?? null;
  const batches = useMemo(() => groupBatches(runs), [runs]);
  const active = batches.find((b) => b.date === pickedDate) ?? batches.at(-1) ?? null;
  const run = active?.attempts.find((a) => a.run_id === pickedRun) ?? active?.attempts[0] ?? null;

  const pickBatch = (date) => {
    setPickedDate(date);
    setPickedRun(null);
  };

  const pickDataset = (name) => {
    const url = new URL(window.location.href);
    url.searchParams.set("dataset", name);
    window.history.replaceState(null, "", url);
    setDataset(name);
    setPickedDate(null);
    setPickedRun(null);
    setHealth(null);
    setRuns([]);
  };

  const title = `${current ? cap(words(current)) : "Orders"} data health`;

  if (!health) {
    return (
      <main className="page">
        <h1 className="title">{title}</h1>
        {error ? (
          <div className="notice" role="alert">
            <p><strong>{error}.</strong></p>
            <p>
              Start the API with <code>uvicorn api.app:app --port 8000</code> and make sure the pipeline has run at
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
        <h1 className="title">{title}</h1>
        <div className="refresh">
          {datasets.length > 1 && (
            <label className="picker">
              <span className="muted">Dataset</span>
              <select value={current ?? ""} onChange={(e) => pickDataset(e.target.value)}>
                {datasets.map((d) => (
                  <option key={d.dataset} value={d.dataset}>{cap(words(d.dataset))} ({d.status})</option>
                ))}
              </select>
            </label>
          )}
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
