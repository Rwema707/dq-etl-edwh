import { day, dayNumber, monthName, num, stateOf, STATE_LABEL } from "../format.js";

const SHOWN = 30;
const MARK = { bad: "✕", warn: "!" };

export default function BatchStrip({ batches, activeDate, onPick }) {
  const shown = batches.slice(-SHOWN);
  if (!shown.length) return null;
  const max = Math.max(...shown.map((b) => b.latest.source_rows || 0), 1);

  return (
    <section aria-labelledby="strip-title" className="strip-section">
      <h2 id="strip-title" className="section-title">Daily batches</h2>
      <div className="strip-box">
        <div className="strip" role="group" aria-label="Daily batches, oldest to newest">
          {shown.map((b, i) => {
            const r = b.latest;
            const state = stateOf(r);
            const h = 10 + Math.round(90 * ((r.source_rows || 0) / max));
            const newMonth = i === 0 || b.date.slice(5, 7) !== shown[i - 1].date.slice(5, 7);
            const label = `${day(b.date)}: ${STATE_LABEL[state]}, ${num(r.source_rows)} rows` +
              (b.attempts.length > 1 ? `, ${b.attempts.length} attempts` : "");
            return (
              <button
                key={b.date}
                type="button"
                className={`tick ${state}${b.date === activeDate ? " active" : ""}`}
                style={{ "--h": `${h}px`, "--i": i }}
                aria-label={label}
                aria-pressed={b.date === activeDate}
                title={label}
                onClick={() => onPick(b.date)}
              >
                <span className="mark" aria-hidden="true">{MARK[state] ?? ""}</span>
                <span className="bar" aria-hidden="true" />
                <span className="tick-day" aria-hidden="true">{dayNumber(b.date)}</span>
                <span className="tick-month" aria-hidden="true">
                  {newMonth ? monthName(b.date) : ""}
                </span>
              </button>
            );
          })}
        </div>
        <ul className="legend">
          <li><i className="swatch ok" /> Loaded</li>
          <li><i className="swatch warn" /> Loaded with warnings</li>
          <li><i className="swatch bad" /> Blocked, nothing loaded</li>
          <li className="muted">Bar height is rows received</li>
        </ul>
      </div>
    </section>
  );
}
