import { useEffect, useState } from "react";
import { getJSON } from "../api.js";
import { num } from "../format.js";

export default function FailedRows({ runId, check, total }) {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getJSON(`/api/runs/${runId}/failures?check=${encodeURIComponent(check)}`)
      .then((r) => !cancelled && setRows(r.map((x) => ({ line: x.csv_line, ...JSON.parse(x.row_json) }))))
      .catch((e) => !cancelled && setError(e.message));
    return () => { cancelled = true; };
  }, [runId, check]);

  if (error) return <p className="notice" role="alert">{error}</p>;
  if (!rows) return <p className="muted">Loading rows…</p>;
  if (!rows.length) return <p className="muted">No rows were stored for this check.</p>;

  const cols = [...new Set(rows.flatMap((r) => Object.keys(r)))];
  return (
    <div className="rows">
      <p className="muted rows-note">
        Showing {rows.length} of {num(total)} failing rows, exactly as delivered. Line is the row's position in the file.
      </p>
      <div className="table-wrap" tabIndex={0} role="region" aria-label="Failing rows">
        <table>
          <thead>
            <tr>{cols.map((c) => <th key={c} scope="col">{c === "line" ? "Line" : c}</th>)}</tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.line}>
                {cols.map((c) => (
                  <td key={c} className={r[c] == null || r[c] === "" ? "empty" : ""}>
                    {r[c] == null || r[c] === "" ? "empty" : String(r[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
