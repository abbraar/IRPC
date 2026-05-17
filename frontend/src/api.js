/**
 * API client.
 * Development: leave VITE_API_BASE_URL unset and use the Vite dev proxy (same origin).
 * Production: set VITE_API_BASE_URL to the FastAPI origin (no trailing slash).
 * Legacy: VITE_API_BASE is still honored if VITE_API_BASE_URL is unset.
 */
function normalizeApiBase() {
  const raw =
    import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_BASE ?? "";
  const s = String(raw).trim().replace(/\/+$/, "");
  return s;
}

const BASE = normalizeApiBase();

async function fetchJson(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || res.statusText);
  }
  return res.json();
}

export function getExcavations() {
  return fetchJson("/excavations");
}

export function getExcavation(id) {
  return fetchJson(`/excavations/${encodeURIComponent(id)}`);
}

export function getInfrastructure() {
  return fetchJson("/infrastructure");
}

export function getProjects() {
  return fetchJson("/projects");
}

export function getIncidents() {
  return fetchJson("/incidents");
}

export function analyzeExcavation(id) {
  return fetchJson(`/analyze/${encodeURIComponent(id)}`, { method: "POST" });
}

export function analyzeLocation(payload) {
  return fetchJson("/analyze-location", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function getDashboardSummary() {
  return fetchJson("/dashboard-summary");
}

export function regenerateData(seed = 42) {
  return fetchJson(`/generate-data?seed=${seed}`, { method: "POST" });
}
