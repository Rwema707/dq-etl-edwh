import { useState } from "react";
import { cap, words } from "../format.js";
import FailedRows from "./FailedRows.jsx";

const ORDER = ["correctness", "completeness", "freshness"];
const GLYPH = { PASS: "✓", FAIL: "✕", SKIPPED: "–" };
const WORD = { PASS: "Passed", FAIL: "Failed", SKIPPED: "Skipped" };

function tone(c) {
  if (c.status === "PASS") return "ok";
  if (c.status === "SKIPPED") return "none";
  return c.severity === "warning" ? "warn" : "bad";
}

function Check({ runId, c, open, onToggle }) {
  const expandable = c.status !== "PASS" || c.expected || c.actual;
  const summary = c.status === "FAIL" ? c.message || c.actual : c.status === "SKIPPED" ? c.message : c.expected || c.actual;
  return (
    <li className="check">
      <button
        type="button"
        className="check-row"
        aria-expanded={expandable ? open : undefined}
        onClick={expandable ? onToggle : undefined}
        disabled={!expandable}
      >
        <span className={`glyph ${tone(c)}`} aria-hidden="true">{GLYPH[c.status]}</span>
        <span className="check-text">
          <span className="check-name">
            {cap(words(c.check_name))}
            {c.status === "FAIL" && c.severity === "warning" && <span className="tag">warning only</span>}
          </span>
          <span className="check-summary">
            <span className="sr-only">{WORD[c.status]}. </span>{summary}
          </span>
        </span>
        {expandable && <span className="chev" aria-hidden="true">{open ? "−" : "+"}</span>}
      </button>
      {open && (
        <div className="check-body">
          <dl className="compare">
            <div><dt>Expected</dt><dd>{c.expected || "–"}</dd></div>
            <div><dt>Found</dt><dd>{c.actual || "–"}</dd></div>
          </dl>
          {c.status === "FAIL" && c.hint && (
            <p className="hint"><strong>What to do first:</strong> {c.hint}</p>
          )}
          {c.status === "FAIL" && c.failed_rows > 0 && (
            <FailedRows runId={runId} check={c.check_name} total={c.failed_rows} />
          )}
        </div>
      )}
    </li>
  );
}

export default function CheckList({ runId, checks }) {
  const firstFail = checks.find((c) => c.status === "FAIL" && c.severity === "blocking")
    ?? checks.find((c) => c.status === "FAIL");
  const [open, setOpen] = useState(() => new Set(firstFail ? [firstFail.check_name] : []));
  const toggle = (name) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(name) ? next.delete(name) : next.add(name);
      return next;
    });

  const pillars = [...new Set([...ORDER, ...checks.map((c) => c.pillar)])]
    .map((p) => ({ p, items: checks.filter((c) => c.pillar === p) }))
    .filter((g) => g.items.length);
  const rank = (c) => (c.status === "FAIL" ? 0 : c.status === "SKIPPED" ? 1 : 2);

  return (
    <div className="checks">
      {pillars.map(({ p, items }) => (
        <section key={p} aria-label={`${cap(p)} checks`}>
          <h3 className="pillar-head">{cap(p)}</h3>
          <ul className="check-list">
            {[...items].sort((a, b) => rank(a) - rank(b)).map((c) => (
              <Check key={c.check_name} runId={runId} c={c}
                     open={open.has(c.check_name)} onToggle={() => toggle(c.check_name)} />
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
