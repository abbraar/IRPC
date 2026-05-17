export const NEIGHBORHOOD_POLYGON = [
  [24.82991436680011, 46.66972979804959],
  [24.833810953932122, 46.6791362811475],
  [24.826761313414863, 46.682807103819854],
  [24.822775263119926, 46.673302295114645],
];

export const NEIGHBORHOOD_CENTER = [
  NEIGHBORHOOD_POLYGON.reduce((sum, point) => sum + point[0], 0) / NEIGHBORHOOD_POLYGON.length,
  NEIGHBORHOOD_POLYGON.reduce((sum, point) => sum + point[1], 0) / NEIGHBORHOOD_POLYGON.length,
];

export const DEFAULT_ZOOM = 16;

export const MAP_BOUNDS = [
  [
    Math.min(...NEIGHBORHOOD_POLYGON.map((point) => point[0])),
    Math.min(...NEIGHBORHOOD_POLYGON.map((point) => point[1])),
  ],
  [
    Math.max(...NEIGHBORHOOD_POLYGON.map((point) => point[0])),
    Math.max(...NEIGHBORHOOD_POLYGON.map((point) => point[1])),
  ],
];

/**
 * Ray-casting point-in-polygon. Vertices are [latitude, longitude] in WGS84 (same order as NEIGHBORHOOD_POLYGON).
 */
function pointInPolygonWgs84(lat, lng, polygon) {
  const n = polygon.length;
  if (n < 3) return false;
  let inside = false;
  for (let i = 0, j = n - 1; i < n; j = i++) {
    const [yi, xi] = polygon[i];
    const [yj, xj] = polygon[j];
    const denom = yj - yi;
    if (denom === 0) continue;
    const intersectsMeridian = (yi > lat) !== (yj > lat);
    const xIntersect = ((xj - xi) * (lat - yi)) / denom + xi;
    if (intersectsMeridian && lng < xIntersect) inside = !inside;
  }
  return inside;
}

/**
 * Fast client-side check: submitted WGS84 point lies inside the configured An Narjis demo polygon.
 * Bounding-box reject first, then exact polygon test.
 */
export function isInsideConfiguredNeighborhood(lat, lng) {
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) return false;
  const [[minLat, minLng], [maxLat, maxLng]] = MAP_BOUNDS;
  if (lat < minLat || lat > maxLat || lng < minLng || lng > maxLng) return false;
  return pointInPolygonWgs84(lat, lng, NEIGHBORHOOD_POLYGON);
}

/** Meters + bearing from a reference [lat, lng] — used for synthetic hotspot offsets. */
function offsetLatLng([lat, lng], meters, bearingDeg) {
  const bearing = (bearingDeg * Math.PI) / 180;
  const metersPerLat = 111320;
  const metersPerLng = metersPerLat * Math.cos((lat * Math.PI) / 180);
  return [
    lat + (meters * Math.cos(bearing)) / metersPerLat,
    lng + (meters * Math.sin(bearing)) / metersPerLng,
  ];
}

function haversineMeters(aLat, aLng, bLat, bLng) {
  const radius = 6371000;
  const toRad = (value) => (value * Math.PI) / 180;
  const dLat = toRad(bLat - aLat);
  const dLng = toRad(bLng - aLng);
  const lat1 = toRad(aLat);
  const lat2 = toRad(bLat);
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** Deterministic PRNG for stable hotspot layouts per input snapshot. */
function createSeededRng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return (s >>> 0) / 0xffffffff;
  };
}

function randomPointInPolygon(rng, bounds, polygon) {
  const [[minLat, minLng], [maxLat, maxLng]] = bounds;
  for (let k = 0; k < 90; k++) {
    const lat = minLat + rng() * (maxLat - minLat);
    const lng = minLng + rng() * (maxLng - minLng);
    if (pointInPolygonWgs84(lat, lng, polygon)) return [lat, lng];
  }
  return null;
}

function collectAttractors(polygon, infrastructure, projects) {
  const out = [];
  const n = polygon.length;
  for (let i = 0; i < n; i++) {
    const [lat1, lng1] = polygon[i];
    const [lat2, lng2] = polygon[(i + 1) % n];
    for (const t of [0.22, 0.48, 0.76]) {
      const lat = lat1 + t * (lat2 - lat1);
      const lng = lng1 + t * (lng2 - lng1);
      if (pointInPolygonWgs84(lat, lng, polygon)) out.push([lat, lng]);
    }
  }
  for (const row of infrastructure ?? []) {
    const la = Number(row.latitude);
    const ln = Number(row.longitude);
    if (Number.isFinite(la) && Number.isFinite(ln) && pointInPolygonWgs84(la, ln, polygon)) {
      out.push([la, ln]);
    }
  }
  for (const row of projects ?? []) {
    const la = Number(row.latitude);
    const ln = Number(row.longitude);
    if (Number.isFinite(la) && Number.isFinite(ln) && pointInPolygonWgs84(la, ln, polygon)) {
      out.push([la, ln]);
    }
  }
  return out;
}

function minSeparationOk(accepted, lat, lng, minMeters) {
  for (const [al, bl] of accepted) {
    if (haversineMeters(lat, lng, al, bl) < minMeters) return false;
  }
  return true;
}

/**
 * Synthetic “existing excavation” hotspots: spread across the demo polygon with mild clustering
 * near infrastructure / projects / corridor samples — not survey data.
 *
 * @param {{ infrastructure?: object[], projects?: object[] }} [ctx]
 * @returns {[number, number][]} WGS84 [lat, lng]
 */
export function buildExcavationHotspots({ infrastructure = [], projects = [] } = {}) {
  const polygon = NEIGHBORHOOD_POLYGON;
  const bounds = MAP_BOUNDS;
  const seed =
    (0xdecafbad ^ (infrastructure.length * 0x9e3779b1) ^ (projects.length * 0x85ebca6b)) >>> 0;
  const rng = createSeededRng(seed);
  const attractors = collectAttractors(polygon, infrastructure, projects);

  const accepted = [];
  const ANCHOR_TARGET = 8;
  const TOTAL_TARGET = 24;
  const ANCHOR_SEP_M = 68;
  const FILL_SEP_M = 30;
  const maxAnchorAttempts = 5000;
  const maxFillAttempts = 12000;
  let anchorAttempts = 0;
  let fillAttempts = 0;

  const tryPush = (lat, lng, minM) => {
    if (!pointInPolygonWgs84(lat, lng, polygon)) return false;
    if (!minSeparationOk(accepted, lat, lng, minM)) return false;
    accepted.push([lat, lng]);
    return true;
  };

  while (accepted.length < ANCHOR_TARGET && anchorAttempts < maxAnchorAttempts) {
    anchorAttempts++;
    const p = randomPointInPolygon(rng, bounds, polygon);
    if (!p) continue;
    let [lat, lng] = p;
    [lat, lng] = offsetLatLng([lat, lng], rng() * 14, rng() * 360);
    tryPush(lat, lng, ANCHOR_SEP_M);
  }

  while (accepted.length < TOTAL_TARGET && fillAttempts < maxFillAttempts) {
    fillAttempts++;
    const roll = rng();
    let lat;
    let lng;

    if (roll < 0.4 || attractors.length === 0) {
      const p = randomPointInPolygon(rng, bounds, polygon);
      if (!p) continue;
      [lat, lng] = p;
    } else if (roll < 0.62 && attractors.length >= 2) {
      const a = attractors[Math.floor(rng() * attractors.length)];
      let b = attractors[Math.floor(rng() * attractors.length)];
      let guard = 0;
      while (haversineMeters(a[0], a[1], b[0], b[1]) < 42 && guard++ < 12) {
        b = attractors[Math.floor(rng() * attractors.length)];
      }
      const w = 0.38 + rng() * 0.32;
      lat = a[0] * w + b[0] * (1 - w);
      lng = a[1] * w + b[1] * (1 - w);
    } else {
      const att = attractors[Math.floor(rng() * attractors.length)];
      const distM = 16 + rng() * 118;
      const brg = rng() * 360;
      [lat, lng] = offsetLatLng(att, distM, brg);
      if (!pointInPolygonWgs84(lat, lng, polygon)) continue;
    }

    [lat, lng] = offsetLatLng([lat, lng], rng() * 11, rng() * 360);
    tryPush(lat, lng, FILL_SEP_M);
  }

  return accepted;
}
