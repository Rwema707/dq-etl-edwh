import { useEffect, useState } from "react";
import { getJSON } from "../api.js";
import { day, num, stateOf, STATE_LABEL, when } from "../format.js";
import CheckList from "./CheckList.jsx";

export default function BatchDetail({ batch, run, onPickRun }) {
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setDetail(null);
    setError(null);
    getJSON(`/api/runs/${run.run_id}`)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [run.run_id]);

  const state = stateOf(run);
  const attempts = [...batch.attempts].reverse(); // oldest first for reading order

  return (
    <section aria-labelledby="detail-title" className="detail">
      <div className="detail-head">
        <h2 id="detail-title" className="section-title big">Batch {day(batch.date)}</h2>
        <span className={`pill ${state}`}>{STATE_LABEL[state]}</span>
      </div>
      <dl className="facts">
        <div><dt>Rows received</dt><dd>{num(run.source_rows)}</dd></div>
        <div><dt>Rows loaded</dt><dd>{num(run.loaded_rows)}</dd></div>
        <div><dt>Finished</dt><dd>{when(run.finished_at)}</dd></div>
        <div><dt>Run</dt><dd className="code">{run.run_id}</dd></div>
      </dl>

      {attempts.length > 1 && (
        <div className="attempts" role="group" aria-label="Attempts for this batch">
          <span className="muted">Attempts</span>
          {attempts.map((a, i) => (
            <button
              key={a.run_id}
              type="button"
              className={`attempt ${a.run_id === run.run_id ? "active" : ""}`}
              aria-pressed={a.run_id === run.run_id}
              onClick={() => onPickRun(a.run_id)}
            >
              {i + 1}. {STATE_LABEL[stateOf(a)].toLowerCase()}
            </button>
          ))}
        </div>
      )}

      {run.error && <p className="notice" role="alert"><strong>Error:</strong> {run.error}</p>}
      {error && <p className="notice" role="alert">{error}</p>}
      {!detail && !error && <p className="muted">Loading checks…</p>}
      {detail && <CheckList runId={run.run_id} checks={detail.checks} />}
    </section>
  );
}
