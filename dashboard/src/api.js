const BASE = import.meta.env?.VITE_API_BASE ?? "";

export async function getJSON(path) {
  let res;
  try {
    res = await fetch(BASE + path);
  } catch {
    throw new Error("Cannot reach the API");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error || `Request failed (${res.status})`);
  }
  return res.json();
}
