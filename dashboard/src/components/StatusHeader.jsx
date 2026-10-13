import { day, num } from "../format.js";

const PILLARS = ["correctness", "completeness", "freshness"];
const PILLAR_STATE = {
  pass: { glyph: "✓", word: "Passing", cls: "ok" },
  warn: { glyph: "!", word: "Warning", cls: "warn" },
  fail: { glyph: "✕", word: "Failing", cls: "bad" },
  unknown: { glyph: "–", word: "Not checked", cls: "none" },
};

function headline(health) {
  const r = health.latest_run;
  if (!r) {
    return { cls: "none", glyph: "–", title: "No batches yet",
      body: "Run the pipeline once to see data health here." };
  }
  const d = day(r.batch_date);
  const good = health.last_successful_batch;
  switch (health.status) {
    case "healthy":
      return { cls: "ok", glyph: "✓", title: `${d} passed every check`,
        body: `${num(r.loaded_rows)} rows were loaded into the warehouse.` };
    case "degraded":
      return { cls: "warn", glyph: "!", title: `${d} loaded, with warnings`,
        body: `${num(r.loaded_rows)} rows were loaded. ${r.warnings} non-blocking ${r.warnings === 1 ? "check needs" : "checks need"} a look.` };
    case "blocked":
      return { cls: "bad", glyph: "✕", title: `${d} was blocked`,
        body: `Nothing from this batch reached the warehouse. ${
          good ? `The latest good batch is ${day(good.batch_date)}.` : "No batch has been loaded yet."}` };
    case "error":
      return { cls: "bad", glyph: "✕", title: `${d} failed unexpectedly`,
        body: r.error || "The pipeline crashed. Check the logs for the run." };
    default:
      return { cls: "none", glyph: "…", title: `${d} is running`, body: "Results will appear when the run finishes." };
  }
}

export default function StatusHeader({ health }) {
  const h = headline(health);
  const failing = health.failing_checks ?? [];
  return (
    <section aria-labelledby="status-title" className="status">
      <div className="status-main">
        <span className={`glyph glyph-lg ${h.cls}`} aria-hidden="true">{h.glyph}</span>
        <div>
          <h2 id="status-title" className="status-title">{h.title}</h2>
          <p className="status-body">{h.body}</p>
        </div>
      </div>
      <ul className="pillars">
        {PILLARS.map((p) => {
          const s = PILLAR_STATE[health.pillars[p] ?? "unknown"];
          const n = failing.filter((c) => c.pillar === p).length;
          return (
            <li key={p} className="pillar">
              <span className="pillar-name">{p}</span>
              <span className={`pillar-state ${s.cls}`}>
                <span aria-hidden="true">{s.glyph}</span> {s.word}
              </span>
              {n > 0 && <span className="muted pillar-count">{n} {n === 1 ? "check" : "checks"} failing</span>}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
