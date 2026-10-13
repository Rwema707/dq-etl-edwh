const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export const monthName = (iso) => MONTHS[Number(iso.slice(5, 7)) - 1];
const timeFmt = new Intl.DateTimeFormat("en-GB", {
  day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
});

export const num = (n) => (n == null ? "–" : Number(n).toLocaleString("en-GB"));
export const day = (iso) => `${Number(iso.slice(8, 10))} ${monthName(iso)}`;
export const dayNumber = (iso) => String(Number(iso.slice(8, 10)));
export const when = (iso) => (iso ? timeFmt.format(new Date(iso)) : "–");
const ACRONYMS = { id: "ID", sla: "SLA" };
export const words = (snake) => snake.split("_").map((w) => ACRONYMS[w] ?? w).join(" ");
export const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

/** Outcome of a run as one of: ok | warn | bad | run */
export function stateOf(run) {
  if (run.status === "SUCCESS") return run.warnings > 0 ? "warn" : "ok";
  if (run.status === "RUNNING") return "run";
  return "bad";
}

export const STATE_LABEL = {
  ok: "Loaded",
  warn: "Loaded with warnings",
  bad: "Blocked",
  run: "Running",
};

/** Group runs (newest first) into batches sorted oldest to newest; attempts newest first. */
export function groupBatches(runs) {
  const byDate = new Map();
  for (const r of runs) {
    if (!byDate.has(r.batch_date)) byDate.set(r.batch_date, []);
    byDate.get(r.batch_date).push(r);
  }
  return [...byDate.entries()]
    .map(([date, attempts]) => ({ date, attempts, latest: attempts[0] }))
    .sort((a, b) => a.date.localeCompare(b.date));
}
