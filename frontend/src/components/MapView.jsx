import { Fragment, useEffect, useMemo, useState } from "react";
import L from "leaflet";
import {
  Circle,
  MapContainer,
  Marker,
  Pane,
  Polygon,
  Polyline,
  Popup,
  ScaleControl,
  TileLayer,
  Tooltip,
  useMap,
} from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { getRiskTheme, getRiskTone } from "../riskTheme.js";
import { getAssetTypeLabel, getAssetMapAbbrev, getIncidentMapAbbrev, getOverlapTypeLabel, getProjectLabel, getProjectMapAbbrev, getSeverityLabel } from "../i18n.js";
import {
  buildExcavationHotspots,
  DEFAULT_ZOOM,
  MAP_BOUNDS,
  NEIGHBORHOOD_CENTER,
  NEIGHBORHOOD_POLYGON,
} from "../neighborhoodConfig.js";

const ASSET_LAYER_KEY = {
  "Gas Pipeline": "gas",
  "Water Pipe": "water",
  "Electrical Cable": "electrical",
  "Telecom Line": "telecom",
};

const UTILITY_LINE_STYLE = {
  "Gas Pipeline": { color: "#f59e0b", weight: 2, opacity: 0.58 },
  "Water Pipe": { color: "#3b82f6", weight: 2, opacity: 0.58 },
  "Electrical Cable": { color: "#ef4444", weight: 2, opacity: 0.58 },
  "Telecom Line": { color: "#2dd4bf", weight: 2, opacity: 0.58 },
};

const LINE_BEARING_BY_TYPE = {
  "Gas Pipeline": 38,
  "Water Pipe": 122,
  "Electrical Cable": 206,
  "Telecom Line": 292,
};

function isFiniteCoordinate(lat, lng) {
  return Number.isFinite(lat) && Number.isFinite(lng);
}

function inputPosition(input) {
  const lat = Number(input?.latitude);
  const lng = Number(input?.longitude);
  return isFiniteCoordinate(lat, lng) ? [lat, lng] : NEIGHBORHOOD_CENTER;
}

function shapeMarkerIcon({ color, label, shape, className = "", variantSecondary = false }) {
  const sh = shape === "square" ? "square" : shape === "triangle" ? "triangle" : "circle";
  const size = shape === "square" ? 26 : shape === "triangle" ? 30 : 32;
  const anchorY = shape === "triangle" ? size - 2 : size / 2;
  const text = label != null ? String(label).trim() : "";
  const showText = text.length > 0;
  const noLabelClass = showText ? "" : " mk-shape--no-label";
  const secondaryClass = variantSecondary ? " mk-shape--secondary" : "";
  return L.divIcon({
    className: `leaflet-risk-marker ${className}`,
    html: `<span class="mk-shape mk-shape--${sh}${noLabelClass}${secondaryClass}" style="--marker-color:${color}">${showText ? text : ""}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, anchorY],
    popupAnchor: [0, -12],
  });
}

function excavationIcon({ color, riskTone }) {
  return L.divIcon({
    className: `leaflet-excavation-marker risk-marker--${riskTone}`,
    html: `<span style="--marker-color:${color}"><b>EXC</b></span>`,
    iconSize: [54, 54],
    iconAnchor: [27, 27],
    popupAnchor: [0, -24],
  });
}

const EXCAVATION_HOTSPOT_ICON = L.divIcon({
  className: "leaflet-excavation-hotspot-wrap",
  html: '<span class="leaflet-excavation-hotspot-dot" aria-hidden="true"></span>',
  iconSize: [20, 20],
  iconAnchor: [10, 10],
  tooltipAnchor: [0, -5],
});

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

function offsetLatLng([lat, lng], meters, bearingDeg) {
  const bearing = (bearingDeg * Math.PI) / 180;
  const metersPerLat = 111320;
  const metersPerLng = metersPerLat * Math.cos((lat * Math.PI) / 180);
  return [
    lat + (meters * Math.cos(bearing)) / metersPerLat,
    lng + (meters * Math.sin(bearing)) / metersPerLng,
  ];
}

function syntheticUtilityPolyline(center, type) {
  const brg = LINE_BEARING_BY_TYPE[type] ?? 48;
  const len = 118;
  return [offsetLatLng(center, len * 0.95, brg), center, offsetLatLng(center, len * 0.92, brg + 180)];
}

function spreadMarkers(items, center, minSpacing = 15) {
  const placed = [];
  return items.map((item, idx) => {
    const nearCenter = haversineMeters(center[0], center[1], item.position[0], item.position[1]) < minSpacing;
    const crowded = placed.some((point) => haversineMeters(point[0], point[1], item.position[0], item.position[1]) < minSpacing);
    const displayPosition = nearCenter || crowded
      ? offsetLatLng(item.position, minSpacing + idx * 2.5, 40 + idx * 137)
      : item.position;
    placed.push(displayPosition);
    return { ...item, displayPosition };
  });
}

function ExcavationFocus({ latitude, longitude, radius, positions, focusKey }) {
  const map = useMap();
  useEffect(() => {
    const bounds = L.latLngBounds(MAP_BOUNDS);
    if (isFiniteCoordinate(latitude, longitude)) {
      bounds.extend(L.latLng(latitude, longitude).toBounds(Math.max(radius * 2.8, 90)));
    }
    positions.forEach((position) => bounds.extend(position));
    map.flyToBounds(bounds, { padding: [34, 34], maxZoom: 18, duration: 0.85 });
  }, [map, focusKey]);
  return null;
}

function severityColor(severity) {
  return getRiskTheme(severity).colorValue;
}

function assetColor(asset) {
  return severityColor(asset.overlap?.severity || asset.criticality || "Low");
}

function projectColor(project) {
  return severityColor(project.overlap?.severity || "Low");
}

function assetItems(source, overlaps) {
  const overlapById = new Map((overlaps ?? []).map((item) => [item.asset_id, item]));
  return (source ?? [])
    .map((asset) => ({
      ...asset,
      position: [Number(asset.latitude), Number(asset.longitude)],
      overlap: overlapById.get(asset.asset_id),
    }))
    .filter((asset) => isFiniteCoordinate(asset.position[0], asset.position[1]));
}

function projectItems(source, overlaps) {
  const overlapById = new Map((overlaps ?? []).map((item) => [item.project_id, item]));
  return (source ?? [])
    .map((project) => ({
      ...project,
      position: [Number(project.latitude), Number(project.longitude)],
      overlap: overlapById.get(project.project_id),
    }))
    .filter((project) => isFiniteCoordinate(project.position[0], project.position[1]));
}

function incidentItems(source) {
  return (source ?? [])
    .map((incident) => ({
      ...incident,
      position: [Number(incident.latitude), Number(incident.longitude)],
    }))
    .filter((incident) => isFiniteCoordinate(incident.position[0], incident.position[1]));
}

function projectMarkerLabel(project, language, t) {
  return getProjectMapAbbrev(project.name, language, t);
}

/** Greedy suppression: farther from excavation loses on-map text when markers crowd (display positions). */
function hiddenMapLabelKeys(excavationPosition, assets, incidents, projects, minSepM) {
  const hidden = new Set();
  if (!isFiniteCoordinate(excavationPosition[0], excavationPosition[1])) return hidden;
  const entries = [
    ...assets.map((a) => ({
      key: `a:${a.asset_id}`,
      pos: a.displayPosition,
      pri: -haversineMeters(excavationPosition[0], excavationPosition[1], a.displayPosition[0], a.displayPosition[1]),
    })),
    ...incidents.map((i) => ({
      key: `i:${i.incident_id}`,
      pos: i.displayPosition,
      pri: -haversineMeters(excavationPosition[0], excavationPosition[1], i.displayPosition[0], i.displayPosition[1]),
    })),
    ...projects.map((p) => ({
      key: `p:${p.project_id}`,
      pos: p.position,
      pri: -haversineMeters(excavationPosition[0], excavationPosition[1], p.position[0], p.position[1]),
    })),
  ].filter((e) => isFiniteCoordinate(e.pos[0], e.pos[1]));
  entries.sort((a, b) => b.pri - a.pri);
  const kept = [];
  for (const e of entries) {
    const conflict = kept.some(([la, ln]) => haversineMeters(la, ln, e.pos[0], e.pos[1]) < minSepM);
    if (conflict) hidden.add(e.key);
    else kept.push(e.pos);
  }
  return hidden;
}

function analysisHasOverlaps(analysis) {
  if (!analysis) return false;
  return (
    (analysis.infrastructure_overlaps?.length ?? 0) +
      (analysis.project_overlaps?.length ?? 0) +
      (analysis.temporal_overlaps?.length ?? 0) >
    0
  );
}

const LEGEND_UTILITY_ROWS = [
  { type: "Gas Pipeline", color: "#f59e0b", labelKey: "gas" },
  { type: "Water Pipe", color: "#3b82f6", labelKey: "water" },
  { type: "Electrical Cable", color: "#ef4444", labelKey: "electrical" },
  { type: "Telecom Line", color: "#2dd4bf", labelKey: "telecom" },
];

function MapLegendInset({ language, t }) {
  const dir = language === "ar" ? "rtl" : "ltr";
  const corridorHint = t("mapLegendCorridorPoc");
  return (
    <aside className="map-legend-inset" dir={dir} aria-label={t("mapLegend")}>
      <div className="map-legend-inset__title">{t("mapLegendInsetTitle")}</div>
      <ul className="map-legend-inset__rows">
        {LEGEND_UTILITY_ROWS.map((row) => (
          <li key={row.type} title={`${getAssetTypeLabel(row.type, language)} — ${corridorHint}`}>
            <span className="map-legend-swatch map-legend-swatch--line" style={{ "--legend-line": row.color }} />
            <span className="map-legend-inset__label">{t(row.labelKey)}</span>
          </li>
        ))}
        <li title={t("mapLegendIncidentHint")}>
          <span className="map-legend-swatch map-legend-swatch--shape map-legend-swatch--incident" aria-hidden />
          <span className="map-legend-inset__label">{t("incidents")}</span>
        </li>
        <li title={t("mapLegendProjectHint")}>
          <span className="map-legend-swatch map-legend-swatch--shape map-legend-swatch--project" aria-hidden />
          <span className="map-legend-inset__label">{t("showProjects")}</span>
        </li>
        <li title={t("mapLegendHotspotHint")}>
          <span className="map-legend-swatch map-legend-swatch--hotspot" aria-hidden />
          <span className="map-legend-inset__label" title={t("layerExistingExcavationsFull")}>
            {t("layerExistingExcavations")}
          </span>
        </li>
      </ul>
    </aside>
  );
}

export default function MapView({
  submittedInput,
  analysis,
  infrastructure = [],
  projects = [],
  layerFilters,
  setLayerFilters,
  busy = false,
  language = "en",
  t = (key) => key,
}) {
  const [mapGuideOpen, setMapGuideOpen] = useState(false);
  const hasAnalysis = Boolean(analysis);
  const analysisState = hasAnalysis ? "analyzed" : busy ? "analyzing" : "idle";
  /** Operational overlays (utilities, projects, incidents, excavation, synthetic lines) only after a successful analysis. */
  const showOperationalLayers = analysisState === "analyzed" && Boolean(analysis);
  const mapInput = analysis?.input ?? submittedInput;
  const excavationPosition = inputPosition(mapInput);
  const workRadius = Number(mapInput?.work_radius ?? 17.6);
  const depthM = Number(mapInput?.depth ?? 0);
  const neighborhood = analysis?.neighborhood_context;
  const isInsideDemoArea = neighborhood?.is_inside_demo_area !== false;
  const boundary = neighborhood?.boundary?.length ? neighborhood.boundary : NEIGHBORHOOD_POLYGON;

  const renderedAssets = assetItems(
    analysis?.context_infrastructure?.length ? analysis.context_infrastructure : infrastructure,
    analysis?.infrastructure_overlaps
  ).filter((asset) => layerFilters?.[ASSET_LAYER_KEY[asset.type]] !== false);
  const renderedProjects =
    layerFilters?.projects === false
      ? []
      : projectItems(analysis?.context_projects?.length ? analysis.context_projects : projects, analysis?.project_overlaps);
  const renderedIncidents = incidentItems(analysis?.context_incidents ?? []);
  const currentRiskLabel = analysis?.risk_level_label || analysis?.risk_level || t("ready");
  const excavationColor = severityColor(analysis?.risk_level || "Low");
  const riskTone = getRiskTone(analysis?.risk_level);
  const displayedAssets = useMemo(
    () =>
      spreadMarkers(
        renderedAssets,
        hasAnalysis ? excavationPosition : NEIGHBORHOOD_CENTER,
        language === "ar" ? 26 : 16
      ),
    [renderedAssets, excavationPosition, hasAnalysis, language]
  );
  const displayedIncidents = useMemo(
    () =>
      spreadMarkers(
        renderedIncidents,
        hasAnalysis ? excavationPosition : NEIGHBORHOOD_CENTER,
        language === "ar" ? 24 : 18
      ),
    [renderedIncidents, excavationPosition, hasAnalysis, language]
  );
  const mapLabelMinSep = language === "ar" ? 30 : 22;
  const hiddenMapLabels = useMemo(
    () =>
      showOperationalLayers
        ? hiddenMapLabelKeys(
            excavationPosition,
            displayedAssets,
            displayedIncidents,
            renderedProjects,
            mapLabelMinSep
          )
        : new Set(),
    [
      showOperationalLayers,
      excavationPosition,
      displayedAssets,
      displayedIncidents,
      renderedProjects,
      mapLabelMinSep,
    ]
  );
  const mapMarkerSecondary = language === "ar";
  const excavationHotspots = useMemo(
    () => buildExcavationHotspots({ infrastructure, projects }),
    [infrastructure, projects]
  );
  const focusPositions = useMemo(
    () => [
      ...renderedAssets.map((asset) => asset.position),
      ...renderedProjects.map((project) => project.position),
      ...renderedIncidents.map((incident) => incident.position),
    ],
    [renderedAssets, renderedProjects, renderedIncidents]
  );
  const focusKey = [
    Number(excavationPosition[0]).toFixed(7),
    Number(excavationPosition[1]).toFixed(7),
    workRadius.toFixed(2),
    analysis?.risk_score ?? "ready",
  ].join("|");
  const toggleLayer = (key) => setLayerFilters?.((prev) => ({ ...prev, [key]: !prev[key] }));

  const utilityLines = useMemo(() => {
    if (!showOperationalLayers) return [];
    const types = new Set();
    renderedAssets.forEach((a) => types.add(a.type));
    const lines = [];
    types.forEach((type) => {
      const key = ASSET_LAYER_KEY[type];
      if (layerFilters?.[key] === false) return;
      const style = UTILITY_LINE_STYLE[type];
      if (!style) return;
      lines.push({
        type,
        positions: syntheticUtilityPolyline(excavationPosition, type),
        pathOptions: {
          color: style.color,
          weight: style.weight,
          opacity: style.opacity,
          lineCap: "round",
          lineJoin: "round",
        },
      });
    });
    return lines;
  }, [showOperationalLayers, renderedAssets, layerFilters, excavationPosition]);

  const hasConflictRing = hasAnalysis && analysisHasOverlaps(analysis);
  const depthConflict = Boolean(analysis?.infrastructure_overlaps?.some((o) => o.depth_conflict));
  const maxAssetDepth = useMemo(() => {
    const depths = (analysis?.infrastructure_overlaps ?? [])
      .map((o) => Number(o.asset_depth))
      .filter((n) => Number.isFinite(n));
    return depths.length ? Math.max(...depths) : 0;
  }, [analysis?.infrastructure_overlaps]);
  const depthMaxRef = Math.max(10, maxAssetDepth > 0 ? maxAssetDepth + 2.5 : 10, depthM || 0);
  const depthBarPct = Math.min(100, depthMaxRef > 0 ? (depthM / depthMaxRef) * 100 : 0);
  const depthWarning = depthConflict || (maxAssetDepth > 0 && depthM >= maxAssetDepth - 0.4);

  return (
    <div className="card map-card">
      <div className="map-card-head">
        <div className="card-heading map-card-title-row">
          <span className="card-icon card-icon--map" aria-hidden />
          <div>
            <h3>{t("internalDigitalTwinView")}</h3>
            <p className="card-subtitle muted small">{t("leafletMapSubtitle")}</p>
          </div>
        </div>
      </div>

      <div className="neighborhood-status-row">
        <span className="neighborhood-badge">{t("demoNeighborhoodConfigured")}</span>
        {!isInsideDemoArea ? <span className="neighborhood-warning">{t("outsideDemoNeighborhood")}</span> : null}
      </div>

      <div className="ops-map-shell ops-map-shell--leaflet" data-analysis-state={analysisState}>
        <div className="layer-filter-panel">
          <span className="muted small">{t("layerFilters")}</span>
          <div className="layer-filter-buttons">
            {[
              ["gas", t("gas")],
              ["water", t("water")],
              ["electrical", t("electrical")],
              ["telecom", t("telecom")],
              ["projects", t("showProjects")],
              ["excavations", t("layerExistingExcavations"), t("layerExistingExcavationsFull")],
            ].map(([key, label, fullLabel]) => (
              <button
                key={key}
                type="button"
                title={fullLabel ?? label}
                className={layerFilters?.[key] === false ? "" : "active"}
                onClick={() => toggleLayer(key)}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="map-north-compass" aria-hidden title={t("mapNorthLabel")}>
          <span className="map-north-compass__arrow">▲</span>
          <span className="map-north-compass__n">{t("mapNorthLabel")}</span>
        </div>

        <MapContainer className="ops-leaflet-map" center={NEIGHBORHOOD_CENTER} zoom={DEFAULT_ZOOM} scrollWheelZoom>
          <ScaleControl position="bottomleft" imperial={false} metric />
          {showOperationalLayers ? (
            <ExcavationFocus
              latitude={excavationPosition[0]}
              longitude={excavationPosition[1]}
              radius={workRadius}
              positions={focusPositions}
              focusKey={focusKey}
            />
          ) : null}
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <Pane name="neighborhood-pane" style={{ zIndex: 350 }}>
            <Polygon
              positions={boundary}
              pathOptions={{
                color: "#38bdf8",
                weight: 2,
                fillColor: "#0ea5e9",
                fillOpacity: 0.08,
                dashArray: "8 6",
              }}
            >
              <Tooltip sticky>{t("demoNeighborhoodConfigured")}</Tooltip>
            </Polygon>
          </Pane>

          <Pane name="excavation-hotspot-pane" style={{ zIndex: 365 }}>
            {layerFilters?.excavations === false
              ? null
              : excavationHotspots.map((position, idx) => (
                  <Marker
                    key={`hotspot-${idx}`}
                    position={position}
                    icon={EXCAVATION_HOTSPOT_ICON}
                    zIndexOffset={40}
                  >
                    <Tooltip direction="top" offset={[0, -6]} opacity={0.92}>
                      {t("excavationHotspotTooltip")}
                    </Tooltip>
                  </Marker>
                ))}
          </Pane>

          <Pane name="utility-line-pane" style={{ zIndex: 390 }}>
            {showOperationalLayers
              ? utilityLines.map((line) => (
                  <Polyline key={line.type} positions={line.positions} pathOptions={line.pathOptions}>
                    <Tooltip sticky opacity={0.92}>
                      {getAssetTypeLabel(line.type, language)}
                    </Tooltip>
                  </Polyline>
                ))
              : null}
          </Pane>

          <Pane name="project-pane" style={{ zIndex: 420 }}>
            {showOperationalLayers
              ? renderedProjects.map((project) => {
              const color = projectColor(project);
              return (
                <Fragment key={project.project_id}>
                  <Circle
                    center={project.position}
                    radius={Number(project.radius_meters ?? 25)}
                    pathOptions={{
                      color,
                      weight: project.overlap ? 2.4 : 1.5,
                      fillColor: color,
                      fillOpacity: project.overlap ? 0.14 : 0.06,
                      dashArray: "9 6",
                    }}
                  >
                    <Tooltip sticky>{getProjectLabel(project.name, language)}</Tooltip>
                    <Popup>
                      <strong>{getProjectLabel(project.name, language)}</strong>
                      <span>
                        {t("scheduleWindow")}: {project.start_date ?? "-"} → {project.end_date ?? "-"}
                      </span>
                      <span>
                        {t("overlapType")}:{" "}
                        {getOverlapTypeLabel(
                          project.overlap?.has_temporal_overlap ? "spatialTemporal" : project.overlap ? "spatialOnly" : "monitoringContext",
                          language
                        )}
                      </span>
                      {project.overlap?.overlap_days ? (
                        <span>
                          {t("scheduleOverlap")}: {project.overlap.overlap_days} {t("dOverlap")}
                        </span>
                      ) : null}
                    </Popup>
                  </Circle>
                  <Marker
                    position={project.position}
                    icon={shapeMarkerIcon({
                      color,
                      label: hiddenMapLabels.has(`p:${project.project_id}`)
                        ? ""
                        : projectMarkerLabel(project, language, t),
                      shape: "square",
                      className: "risk-marker--project",
                      variantSecondary: mapMarkerSecondary,
                    })}
                    zIndexOffset={mapMarkerSecondary ? 88 : 115}
                  >
                    <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                      {getProjectLabel(project.name, language)}
                    </Tooltip>
                  </Marker>
                </Fragment>
              );
            })
            : null}
          </Pane>

          <Pane name="asset-pane" style={{ zIndex: 520 }}>
            {showOperationalLayers
              ? displayedAssets.map((asset) => {
              const color = assetColor(asset);
              const abbr = getAssetMapAbbrev(asset.type, language, t);
              const pinLabel = hiddenMapLabels.has(`a:${asset.asset_id}`) ? "" : abbr;
              return (
                <Fragment key={asset.asset_id}>
                  <Circle
                    center={asset.position}
                    radius={Number(asset.influence_radius ?? 8)}
                    pathOptions={{
                      color,
                      weight: asset.overlap ? 2 : 1.4,
                      fillColor: color,
                      fillOpacity: asset.overlap ? 0.16 : 0.07,
                      dashArray: "6 5",
                    }}
                  />
                  <Marker
                    position={asset.displayPosition}
                    icon={shapeMarkerIcon({
                      color,
                      label: pinLabel,
                      shape: "circle",
                      className: "risk-marker--asset",
                      variantSecondary: mapMarkerSecondary,
                    })}
                    zIndexOffset={mapMarkerSecondary ? 95 : 120}
                  >
                    <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                      {getAssetTypeLabel(asset.type, language)}
                    </Tooltip>
                    <Popup>
                      <strong>{getAssetTypeLabel(asset.type, language)}</strong>
                      <span>
                        {t("criticality")}: {getSeverityLabel(asset.criticality, language)}
                      </span>
                      {asset.overlap?.distance_meters ? <span>{t("distance")}: {asset.overlap.distance_meters} m</span> : null}
                      <span>
                        {t("influenceRadius")}: {Number(asset.influence_radius ?? 0).toFixed(1)} m
                      </span>
                      {asset.overlap?.severity ? (
                        <span>
                          {t("overlapSeverity")}: {getSeverityLabel(asset.overlap.severity, language)}
                        </span>
                      ) : null}
                    </Popup>
                  </Marker>
                </Fragment>
              );
            })
              : null}
          </Pane>

          <Pane name="incident-pane" style={{ zIndex: 560 }}>
            {showOperationalLayers
              ? displayedIncidents.map((incident) => (
              <Marker
                key={incident.incident_id}
                position={incident.displayPosition}
                icon={shapeMarkerIcon({
                  color: "#a78bfa",
                  label: hiddenMapLabels.has(`i:${incident.incident_id}`)
                    ? ""
                    : getIncidentMapAbbrev(language, t),
                  shape: "triangle",
                  className: "risk-marker--incident",
                  variantSecondary: mapMarkerSecondary,
                })}
                zIndexOffset={mapMarkerSecondary ? 65 : 80}
              >
                <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                  {language === "ar"
                    ? `${t("incidents")} · ${getSeverityLabel(incident.severity, language)} · ${getAssetTypeLabel(incident.related_asset_type, language)}`
                    : t("incidents")}
                </Tooltip>
                <Popup>
                  <strong>{t("incidents")}</strong>
                  <span>
                    {t("overlapSeverity")}: {getSeverityLabel(incident.severity, language)}
                  </span>
                  <span>
                    {t("infrastructure")}: {getAssetTypeLabel(incident.related_asset_type, language)}
                  </span>
                </Popup>
              </Marker>
            ))
              : null}
          </Pane>

          <Pane name="excavation-pane" style={{ zIndex: 720 }}>
            {showOperationalLayers && isFiniteCoordinate(excavationPosition[0], excavationPosition[1]) ? (
              <>
                <Circle
                  center={excavationPosition}
                  radius={Math.max(workRadius * 1.74, workRadius + 52)}
                  pathOptions={{
                    color: "#94a3b8",
                    weight: 1.35,
                    dashArray: "12 9",
                    fillColor: "#64748b",
                    fillOpacity: 0.05,
                    opacity: 0.72,
                  }}
                >
                  <Tooltip direction="top" opacity={0.95}>
                    {t("mapAwarenessZone")}
                  </Tooltip>
                </Circle>
                <Circle
                  center={excavationPosition}
                  radius={Math.max(1, workRadius)}
                  pathOptions={{
                    className: `leaflet-excavation-radius leaflet-excavation-radius--${riskTone}`,
                    color: excavationColor,
                    weight: 3.4,
                    fillColor: "#38bdf8",
                    fillOpacity: 0.15,
                  }}
                >
                  <Tooltip direction="top" offset={[0, -12]} opacity={0.95}>
                    <strong>{t("mapWorkRadiusZone")}</strong>
                    <span>
                      {workRadius.toFixed(1)} m · {currentRiskLabel}
                    </span>
                  </Tooltip>
                </Circle>
                {hasConflictRing ? (
                  <Circle
                    center={excavationPosition}
                    radius={Math.max(11, workRadius * 0.5)}
                    pathOptions={{
                      color: "#ef4444",
                      weight: 2,
                      dashArray: "7 6",
                      fillColor: "#ef4444",
                      fillOpacity: 0.1,
                      opacity: 0.88,
                    }}
                  >
                    <Tooltip direction="center" opacity={0.95}>
                      {t("mapCriticalOverlapZone")}
                    </Tooltip>
                  </Circle>
                ) : null}
                <Marker
                  position={excavationPosition}
                  icon={excavationIcon({ color: excavationColor, riskTone })}
                  zIndexOffset={1000}
                >
                  <Tooltip
                    direction={language === "ar" ? "left" : "right"}
                    offset={language === "ar" ? [-20, 0] : [20, 0]}
                    opacity={0.96}
                  >
                    <strong>{currentRiskLabel}</strong>
                    <span>
                      {t("workRadius")}: {workRadius.toFixed(1)} m
                    </span>
                    <span>
                      {t("depth")}: {Number(mapInput?.depth ?? 0).toFixed(2)} m
                    </span>
                  </Tooltip>
                  <Popup>
                    <strong>{t("submittedExcavationSite")}</strong>
                    <span>
                      {t("depth")}: {Number(mapInput?.depth ?? 0).toFixed(2)} m
                    </span>
                    <span>
                      {t("workRadius")}: {workRadius.toFixed(1)} m
                    </span>
                    <span>
                      {t("currentRisk")}: {currentRiskLabel}
                    </span>
                    <span>
                      {t("scheduleWindow")}: {mapInput?.start_date ?? "-"} → {mapInput?.end_date ?? "-"}
                    </span>
                  </Popup>
                </Marker>
              </>
            ) : null}
          </Pane>
        </MapContainer>
        <div className="map-overlay-stack map-overlay-stack--end" dir={language === "ar" ? "rtl" : "ltr"}>
          <div className="map-guide-footer map-guide-footer--overlay">
            <button
              type="button"
              className="map-guide-toggle"
              aria-expanded={mapGuideOpen}
              onClick={() => setMapGuideOpen((open) => !open)}
            >
              {mapGuideOpen ? t("mapGuideToggleClose") : t("mapGuideToggleOpen")}
            </button>
            {mapGuideOpen ? (
              <div className="map-guide-panel muted small">
                <p className="map-guide-panel__intro">{t("mapGuideIntro")}</p>
                <p>{t("mapSymRings")}</p>
                <p>{t("mapSymMarkers")}</p>
                <p>{t("mapSymLines")}</p>
              </div>
            ) : null}
          </div>
          <p className="map-caption map-caption--overlay muted small">{t("leafletMapCaption")}</p>
          {hasAnalysis ? (
            <div className="map-depth-strip map-depth-strip--overlay" dir={language === "ar" ? "rtl" : "ltr"}>
              <span className="map-depth-strip__title muted small">{t("mapDepthTitle")}</span>
              <div className="map-depth-strip__track" aria-hidden>
                <div
                  className={`map-depth-strip__fill ${depthWarning ? "map-depth-strip__fill--warn" : ""}`}
                  style={{ width: `${depthBarPct}%` }}
                />
              </div>
              <p className="map-depth-strip__value muted small">
                {depthM.toFixed(2)} {language === "ar" ? "م" : "m"} / {depthMaxRef.toFixed(1)}{" "}
                {language === "ar" ? "م" : "m"} {t("mapDepthMaxLabel")} —{" "}
                {depthWarning ? t("mapDepthNearAsset") : t("mapDepthOk")}
              </p>
            </div>
          ) : null}
          <MapLegendInset language={language} t={t} />
        </div>
        {busy && !hasAnalysis ? (
          <div className="map-analysis-processing" role="status" aria-live="polite">
            <span aria-hidden />
            <strong>{t("analyzingLocation")}</strong>
            <small>{t("mapAnalysisPending")}</small>
          </div>
        ) : null}
      </div>
    </div>
  );
}
