import { useCallback, useEffect, useMemo, useState } from "react";
import {
  analyzeLocation,
  getDashboardSummary,
  getIncidents,
  getInfrastructure,
  getProjects,
  regenerateData,
} from "../api.js";
import AiCopilotPanel from "./AiCopilotPanel.jsx";
import AnalysisPipeline from "./AnalysisPipeline.jsx";
import ExplanationPanel from "./ExplanationPanel.jsx";
import MapView from "./MapView.jsx";
import RecommendationPanel from "./RecommendationPanel.jsx";
import RiskCard from "./RiskCard.jsx";
import TimelineView from "./TimelineView.jsx";
import { getAssetTypeLabel, getProjectLabel, getSeverityLabel, makeTranslator, riskLabel } from "../i18n.js";
import { isInsideConfiguredNeighborhood } from "../neighborhoodConfig.js";
import { getRiskTheme, riskCssVars } from "../riskTheme.js";

const DEFAULT_FORM = {
  longitude: "46.676244",
  latitude: "24.828315",
  depth: "4.85",
  work_radius: "17.6",
  start_date: "2026-05-12",
  end_date: "2026-06-19",
};

const DEFAULT_LAYERS = {
  gas: true,
  water: true,
  electrical: true,
  telecom: true,
  projects: true,
  excavations: true,
};

const eventPools = {
  calm: [
    "eventMonitoringNominal",
    "eventNoActiveOverlap",
    "eventProjectResolved",
    "eventUtilityClearancePending",
    "eventPermitWorkflowReady",
  ],
  elevated: [
    "eventUtilityThreshold",
    "eventTelecomConflict",
    "eventOverlapWarning",
    "eventVibration",
    "eventFiberOwnership",
    "eventMaintenancePermitOverlap",
    "eventCoordinationReview",
  ],
  high: [
    "eventGasPressure",
    "eventRiskHigh",
    "eventFieldEngineeringReview",
    "eventEnvironmentalThreshold",
    "eventMaintenancePermitOverlap",
    "eventUtilityClearancePending",
  ],
};

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function overlapCount(analysis) {
  if (!analysis) return 0;
  return (
    (analysis.infrastructure_overlaps?.length ?? 0) +
    (analysis.project_overlaps?.length ?? 0) +
    (analysis.temporal_overlaps?.length ?? 0)
  );
}

function eventSeverity(analysis, idx) {
  if (!analysis) return "INFO";
  if (analysis.risk_level === "High") return idx % 3 === 0 ? "CRITICAL" : "WARNING";
  if (overlapCount(analysis) > 0 || analysis.risk_level === "Medium") return idx % 4 === 0 ? "WARNING" : "INFO";
  return "INFO";
}

function nextEventKey(analysis, idx) {
  const pool = !analysis
    ? eventPools.calm
    : analysis.risk_level === "High"
      ? eventPools.high
      : overlapCount(analysis) > 0
        ? eventPools.elevated
        : eventPools.calm;
  return pool[idx % pool.length];
}

function buildChangeSummary(previous, current, t) {
  if (!previous || !current) return { title: t("noPreviousAnalysis"), lines: [] };
  const changes = [];
  const prevInput = previous.input;
  const currentInput = current.input;
  if (prevInput.longitude !== currentInput.longitude || prevInput.latitude !== currentInput.latitude) {
    changes.push(t("coordinatesChanged"));
  }
  if (Number(prevInput.work_radius) !== Number(currentInput.work_radius)) {
    changes.push(`${t("workRadiusChanged")}: ${prevInput.work_radius}m → ${currentInput.work_radius}m`);
  }
  if (Number(prevInput.depth) !== Number(currentInput.depth)) {
    changes.push(`${t("depthChanged")}: ${prevInput.depth}m → ${currentInput.depth}m`);
  }
  if (prevInput.start_date !== currentInput.start_date || prevInput.end_date !== currentInput.end_date) {
    changes.push(t("scheduleChanged"));
  }
  const prevOverlaps = overlapCount(previous);
  const currentOverlaps = overlapCount(current);
  if (currentOverlaps !== prevOverlaps) {
    changes.push(`${t("overlapCountChanged")}: ${prevOverlaps} → ${currentOverlaps}`);
  }
  if (currentOverlaps > prevOverlaps) {
    changes.push(t("newOverlapDetected"));
  }
  return {
    title: `${t("riskChangedFrom")} ${previous.risk_level_label || previous.risk_level} → ${current.risk_level_label || current.risk_level}`,
    lines: changes.length ? changes : [t("noMaterialChange")],
  };
}

function buildTimeline(analysis, t) {
  if (!analysis) return [];
  const base = Number(analysis.risk_score ?? 0);
  const temporal = analysis.temporal_overlaps?.length ?? 0;
  const infra = analysis.infrastructure_overlaps?.length ?? 0;
  const points = [
    { day: 1, score: Math.max(0, Math.min(100, base - 8)), note: analysis.risk_level_label || riskLabel(analysis.risk_level, t) },
    { day: 3, score: Math.max(0, Math.min(100, base + temporal * 3)), note: temporal ? t("scheduleOverlap") : t("monitoringReliability") },
    { day: 6, score: Math.max(0, Math.min(100, base + infra * 2 + temporal * 4)), note: infra || temporal ? t("criticalOverlap") : t("eventMonitoringNominal") },
    { day: 10, score: Math.max(0, Math.min(100, base - 12 + temporal)), note: t("conflictResolved") },
  ];
  return points.map((p) => ({
    ...p,
    level: p.score > 70 ? t("highRisk") : p.score > 30 ? t("mediumRisk") : t("lowRisk"),
  }));
}

function operationalStatus(analysis, t) {
  const theme = getRiskTheme(analysis?.risk_level);
  const label =
    theme.tone === "high" ? t("statusCritical") : theme.tone === "medium" ? t("statusElevatedRisk") : t("statusNormal");
  return { ...theme, label };
}

function WorkflowStrip({ hasAnalysis, busy, t }) {
  const steps = [
    { n: 1, label: t("enterWgs84Location"), done: true, active: !hasAnalysis },
    { n: 2, label: t("analyzeSpatialTemporalRisk"), done: hasAnalysis, active: busy },
    { n: 3, label: t("reviewOutput"), done: hasAnalysis, active: hasAnalysis && !busy },
  ];
  return (
    <div className="workflow-strip" aria-label="Analysis workflow">
      {steps.map((s, i) => (
        <div
          key={s.n}
          className={`workflow-step ${s.done ? "workflow-step--done" : ""} ${s.active ? "workflow-step--active" : ""}`}
        >
          <span className="workflow-num" aria-hidden>
            {s.done ? "✓" : s.n}
          </span>
          <span className="workflow-label">{s.label}</span>
          {i < steps.length - 1 ? <span className="workflow-connector" aria-hidden /> : null}
        </div>
      ))}
    </div>
  );
}

function LocationForm({ form, setForm, onSubmit, busy, t, highlightCoordsOutsideDemo, coordShakeNonce, onCoordinateFieldChange }) {
  const [coordShakePlay, setCoordShakePlay] = useState(false);

  useEffect(() => {
    if (!coordShakeNonce) return undefined;
    setCoordShakePlay(true);
    const id = window.setTimeout(() => setCoordShakePlay(false), 480);
    return () => window.clearTimeout(id);
  }, [coordShakeNonce]);

  const update = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  const updateCoord = (key) => (event) => {
    onCoordinateFieldChange?.();
    setForm((prev) => ({ ...prev, [key]: event.target.value }));
  };

  const formClass = [
    "card",
    "location-form",
    "card-accent",
    highlightCoordsOutsideDemo ? "location-form--coord-warn" : "",
    coordShakePlay ? "location-form--coord-shake" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <form className={formClass} onSubmit={onSubmit}>
      <div className="card-heading">
        <span className="card-icon card-icon--pin" aria-hidden />
        <div>
          <h3>{t("manualExcavationInput")}</h3>
          <p className="card-subtitle muted small">{t("coordinateFormat")}</p>
        </div>
      </div>
      <div className="form-grid">
        <div
          className={`coord-field-pair${highlightCoordsOutsideDemo ? " coord-field-pair--invalid" : ""}`}
          aria-invalid={highlightCoordsOutsideDemo || undefined}
        >
          <label>
            <span>{t("longitude")}</span>
            <input
              className="numeric-input"
              dir="ltr"
              value={form.longitude}
              onChange={updateCoord("longitude")}
              inputMode="decimal"
              autoComplete="off"
            />
          </label>
          <label>
            <span>{t("latitude")}</span>
            <input
              className="numeric-input"
              dir="ltr"
              value={form.latitude}
              onChange={updateCoord("latitude")}
              inputMode="decimal"
              autoComplete="off"
            />
          </label>
        </div>
        <label>
          <span>{t("depthMeters")}</span>
          <input className="numeric-input" dir="ltr" value={form.depth} onChange={update("depth")} inputMode="decimal" />
        </label>
        <label>
          <span>{t("workRadiusMeters")}</span>
          <input className="numeric-input" dir="ltr" value={form.work_radius} onChange={update("work_radius")} inputMode="decimal" />
        </label>
        <label>
          <span>{t("startDate")}</span>
          <input className="numeric-input" dir="ltr" type="date" value={form.start_date} onChange={update("start_date")} />
        </label>
        <label>
          <span>{t("endDate")}</span>
          <input className="numeric-input" dir="ltr" type="date" value={form.end_date} onChange={update("end_date")} />
        </label>
      </div>
      <button type="submit" className="btn primary location-submit" disabled={busy}>
        {busy ? t("analyzingLocation") : t("analyzeLocationRisk")}
      </button>
    </form>
  );
}

function OverlapLists({ analysis, language, t }) {
  const infrastructure = analysis?.infrastructure_overlaps ?? [];
  const projects = analysis?.project_overlaps ?? [];
  const temporal = analysis?.temporal_overlaps ?? [];

  return (
    <div className="card overlap-card">
      <div className="card-heading">
        <span className="card-icon card-icon--alert" aria-hidden />
        <div>
          <h3>{t("detectedOverlaps")}</h3>
          <p className="card-subtitle muted small">{t("overlapsSubtitle")}</p>
        </div>
      </div>
      <div className="overlap-grid">
        <OverlapSection title={t("infrastructure")} items={infrastructure} empty={t("noInfrastructureOverlap")} language={language} t={t} />
        <OverlapSection title={t("projects")} items={projects} empty={t("noProjectOverlap")} language={language} t={t} />
        <OverlapSection title={t("temporal")} items={temporal} empty={t("noTemporalOverlap")} language={language} t={t} />
      </div>
    </div>
  );
}

function overlapDisplayName(item, language) {
  if (item.type) return getAssetTypeLabel(item.type, language);
  return getProjectLabel(item.name || item.project_name, language);
}

function OverlapSection({ title, items, empty, language, t }) {
  return (
    <section className="conflict-section">
      <div className="conflict-section-head">
        <h4>{title}</h4>
        <span className="chip chip--neutral">{items.length} {items.length === 1 ? t("item") : t("items")}</span>
      </div>
      {items.length === 0 ? (
        <p className="muted small conflict-empty">{empty}</p>
      ) : (
        <ul className="conflict-list">
          {items.map((item) => (
            <li key={item.asset_id || item.project_id || `${title}-${item.name}`}>
              <span className={`sev sev-${String(item.severity || "Low").toLowerCase()}`}>
                {getSeverityLabel(item.severity || "Low", language)}
              </span>
              <span className="conflict-body">
                <strong>{overlapDisplayName(item, language)}</strong>
                <span className="muted small">
                  {item.distance_meters ? `${item.distance_meters} m` : `${item.overlap_days} ${t("dOverlap")}`}
                  {item.criticality ? ` · ${getSeverityLabel(item.criticality, language)} ${t("criticality")}` : ""}
                  {item.has_temporal_overlap ? ` · ${t("spatialTemporal")}` : ""}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function OperationalEventStream({ analysis, events, t }) {
  return (
    <div className="card ops-card event-stream-card">
      <div className="card-heading">
        <span className="card-icon card-icon--ai" aria-hidden />
        <div>
          <h3>{t("liveEventStream")}</h3>
          <p className="card-subtitle muted small">{t("liveEventSubtitle")}</p>
        </div>
      </div>
      <div className={`stream-status stream-status--${String(analysis?.risk_level || "low").toLowerCase()}`}>
        {analysis ? `${analysis.risk_level_label || analysis.risk_level} · ${analysis.risk_score}/100` : t("ready")}
      </div>
      <div className="event-stream-list">
        {events.length ? (
          events.map((event) => (
            <div key={event.id} className={`event-row event-row--${event.severity.toLowerCase()}`}>
              <span className="event-time mono">{event.time}</span>
              <span className="event-severity">{event.severity}</span>
              <span className="event-message">{event.message}</span>
            </div>
          ))
        ) : (
          <p className="muted small">{t("noLiveEvents")}</p>
        )}
      </div>
    </div>
  );
}

function RiskTimelineSimulation({ analysis, timeline, onSimulate, t }) {
  return (
    <div className="card ops-card timeline-sim-card">
      <div className="card-heading">
        <span className="card-icon card-icon--gauge" aria-hidden />
        <div>
          <h3>{t("riskEvolution")}</h3>
          <p className="card-subtitle muted small">{t("riskEvolutionHint")}</p>
        </div>
      </div>
      <button type="button" className="btn ghost ops-action" onClick={onSimulate} disabled={!analysis}>
        {t("simulateTimeline")}
      </button>
      <div className="risk-evolution-chart">
        {(timeline.length ? timeline : buildTimeline(analysis, t)).map((point) => (
          <div key={point.day} className="risk-evolution-point">
            <div className="risk-evolution-meta">
              <strong>{t("day")} {point.day}</strong>
              <span className="muted small">{point.note}</span>
            </div>
            <div className="risk-evolution-track" aria-hidden>
              <span style={{ width: `${point.score}%` }} />
            </div>
            <span className="risk-evolution-score">{Math.round(point.score)} · {point.level}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function WhatChangedPanel({ previousAnalysis, analysis, t }) {
  const summary = buildChangeSummary(previousAnalysis, analysis, t);
  return (
    <div className="card ops-card what-changed-card">
      <div className="card-heading">
        <span className="card-icon card-icon--doc" aria-hidden />
        <div>
          <h3>{t("whatChanged")}</h3>
          <p className="card-subtitle muted small">{t("because")}</p>
        </div>
      </div>
      <strong className="what-changed-title">{summary.title}</strong>
      {summary.lines.length ? (
        <ul className="what-changed-list">
          {summary.lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

function exportSnapshot({ analysis, language, t }) {
  if (!analysis) return;
  const snapshot = {
    title: t("excavationRiskAssessment"),
    exported_at: new Date().toISOString(),
    language,
    input: analysis.input,
    risk: {
      score: analysis.risk_score,
      level: analysis.risk_level,
      label: analysis.risk_level_label,
      confidence_score: analysis.confidence_score,
    },
    detected_overlaps: {
      infrastructure: analysis.infrastructure_overlaps,
      projects: analysis.project_overlaps,
      temporal: analysis.temporal_overlaps,
    },
    explanation: analysis.explanation,
    recommendations: analysis.recommendations,
    neighborhood_context: analysis.neighborhood_context,
    transparency_note: t("pocTransparencyNote"),
  };
  const blob = new Blob([JSON.stringify(snapshot, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `excavation-risk-snapshot-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.json`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

export default function Dashboard() {
  const [infrastructure, setInfrastructure] = useState([]);
  const [projects, setProjects] = useState([]);
  const [incidents, setIncidents] = useState([]);
  const [form, setForm] = useState(DEFAULT_FORM);
  const [analysis, setAnalysis] = useState(null);
  const [previousAnalysis, setPreviousAnalysis] = useState(null);
  const [lastAnalyzedInput, setLastAnalyzedInput] = useState(DEFAULT_FORM);
  const [language, setLanguage] = useState("en");
  const [events, setEvents] = useState([]);
  const [timeline, setTimeline] = useState([]);
  const [layerFilters, setLayerFilters] = useState(DEFAULT_LAYERS);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [coordinatesOutsideDemo, setCoordinatesOutsideDemo] = useState(false);
  const [coordShakeNonce, setCoordShakeNonce] = useState(0);
  const [pipelineStepIndex, setPipelineStepIndex] = useState(0);
  const t = useMemo(() => makeTranslator(language), [language]);
  const status = operationalStatus(analysis, t);
  const statusStyle = riskCssVars(analysis?.risk_level);

  const refresh = useCallback(async () => {
    setError(null);
    const [infra, projectRows, incidentRows, dash] = await Promise.all([
      getInfrastructure(),
      getProjects(),
      getIncidents(),
      getDashboardSummary(),
    ]);
    setInfrastructure(infra);
    setProjects(projectRows);
    setIncidents(incidentRows);
    setSummary(dash);
  }, []);

  useEffect(() => {
    setLoading(true);
    refresh()
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [refresh]);

  useEffect(() => {
    if (!busy) {
      setPipelineStepIndex(0);
      return undefined;
    }
    const interval = window.setInterval(() => {
      setPipelineStepIndex((prev) => (prev + 1) % 6);
    }, 280);
    return () => window.clearInterval(interval);
  }, [busy]);

  useEffect(() => {
    const addEvent = () => {
      setEvents((prev) => {
        const idx = prev[0]?.seq ? prev[0].seq + 1 : 1;
        const severity = eventSeverity(analysis, idx);
        const message = t(nextEventKey(analysis, idx));
        const next = {
          id: `${Date.now()}-${idx}`,
          seq: idx,
          time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          severity,
          message,
        };
        return [next, ...prev].slice(0, 18);
      });
    };
    addEvent();
    const interval = window.setInterval(addEvent, analysis?.risk_level === "High" ? 2600 : 4200);
    return () => window.clearInterval(interval);
  }, [analysis, t]);

  const hasAnalysis = Boolean(analysis);
  const risk = analysis
    ? {
        risk_score: analysis.risk_score,
        risk_level: analysis.risk_level,
        confidence_score: analysis.confidence_score,
        confidence_rationale: t("confidenceLocal"),
        contributing_factors: analysis.contributing_factors,
        risk_level_label: analysis.risk_level_label,
      }
    : null;
  const analysisForCopilot = analysis
    ? {
        risk,
        conflicts: {
          spatial: [
            ...analysis.infrastructure_overlaps.map((item) => ({
              severity: item.severity,
              target_name: item.type,
            })),
            ...analysis.project_overlaps.map((item) => ({
              severity: item.severity,
              target_name: item.name,
            })),
          ],
          temporal: analysis.temporal_overlaps.map((item) => ({
            severity: item.severity,
            project_name: item.name,
          })),
        },
        recommendations: analysis.recommendations,
      }
    : null;
  const intelligence = useMemo(() => {
    const total = summary?.total_requests || 0;
    const typeCounts = infrastructure.reduce((acc, item) => {
      acc[item.type] = (acc[item.type] || 0) + 1;
      return acc;
    }, {});
    const topInfraType =
      Object.entries(typeCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || t("noAssets");
    const activeProjects = projects.filter((p) => String(p.status).toLowerCase() === "active").length;
    const density = total ? (incidents.length / total).toFixed(1) : "0.0";
    return {
      highestRisk: analysis ? `${analysis.risk_level_label || riskLabel(analysis.risk_level, t)} (${analysis.risk_score})` : t("awaitingInput"),
      hotspotDensity: density,
      activeOverlaps: analysis?.project_overlaps?.length ?? activeProjects,
      topInfraType: getAssetTypeLabel(topInfraType, language),
    };
  }, [analysis, incidents.length, infrastructure, language, projects, summary, t]);

  const runAnalysis = async (event) => {
    event.preventDefault();
    setError(null);
    const payload = {
      longitude: Number(form.longitude),
      latitude: Number(form.latitude),
      depth: Number(form.depth),
      work_radius: Number(form.work_radius),
      start_date: form.start_date,
      end_date: form.end_date,
      language,
    };
    if (
      !Number.isFinite(payload.longitude) ||
      !Number.isFinite(payload.latitude) ||
      !Number.isFinite(payload.depth) ||
      !Number.isFinite(payload.work_radius) ||
      payload.depth <= 0 ||
      payload.work_radius <= 0 ||
      !payload.start_date ||
      !payload.end_date
    ) {
      setCoordinatesOutsideDemo(false);
      setError(t("validInputError"));
      return;
    }
    if (!isInsideConfiguredNeighborhood(payload.latitude, payload.longitude)) {
      setCoordinatesOutsideDemo(true);
      setCoordShakeNonce((n) => n + 1);
      return;
    }
    setCoordinatesOutsideDemo(false);
    setBusy(true);
    try {
      const [res] = await Promise.all([analyzeLocation(payload), delay(1700)]);
      setPreviousAnalysis(analysis);
      setAnalysis(res);
      setLastAnalyzedInput(res.input);
      setTimeline([]);
      const dash = await getDashboardSummary();
      setSummary(dash);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const switchLanguage = async (nextLanguage) => {
    if (!analysis) {
      setLanguage(nextLanguage);
      return;
    }
    setError(null);
    const payload = {
      longitude: Number(lastAnalyzedInput.longitude),
      latitude: Number(lastAnalyzedInput.latitude),
      depth: Number(lastAnalyzedInput.depth),
      work_radius: Number(lastAnalyzedInput.work_radius),
      start_date: lastAnalyzedInput.start_date,
      end_date: lastAnalyzedInput.end_date,
      language: nextLanguage,
    };
    if (
      !Number.isFinite(payload.longitude) ||
      !Number.isFinite(payload.latitude) ||
      !isInsideConfiguredNeighborhood(payload.latitude, payload.longitude)
    ) {
      setError(t("coordinatesOutsideDemoMessage"));
      return;
    }
    setLanguage(nextLanguage);
    setBusy(true);
    try {
      const res = await analyzeLocation(payload);
      setAnalysis(res);
      setLastAnalyzedInput(res.input);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const regen = async () => {
    setBusy(true);
    setError(null);
    try {
      await regenerateData(Math.floor(Math.random() * 1e6));
      setAnalysis(null);
      setPreviousAnalysis(null);
      setTimeline([]);
      await refresh();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const simulateTimeline = () => {
    setTimeline(buildTimeline(analysis, t));
  };
  const handleExportSnapshot = () => exportSnapshot({ analysis, language, t });
  const locationStatusLabel = analysis ? analysis.risk_level_label || riskLabel(analysis.risk_level, t) : t("ready");

  return (
    <div className="dashboard" dir={language === "ar" ? "rtl" : "ltr"} lang={language}>
      <header className="topbar">
        <div className="topbar-brand">
          <p className="eyebrow">{t("digitalTwinPoc")}</p>
          <h1>{t("excavationRiskAssessment")}</h1>
          <p className="subtitle">
            {t("subtitle")}
          </p>
        </div>
        <div className="top-actions">
          <div
            className={`operational-status risk-tone--${status.tone}`}
            style={statusStyle}
            aria-live="polite"
          >
            <span className="status-beacon" aria-hidden />
            <span className="status-copy">
              <span>{t("operationalStatus")}</span>
              <strong>{status.label}</strong>
            </span>
          </div>
          <button type="button" className="btn ghost" onClick={handleExportSnapshot} disabled={!analysis}>
            {t("exportSnapshot")}
          </button>
          <div className="language-toggle" role="group" aria-label="Language">
            <button
              type="button"
              className={language === "en" ? "active" : ""}
              onClick={() => switchLanguage("en")}
              disabled={busy}
            >
              {t("languageEnglish")}
            </button>
            <button
              type="button"
              className={language === "ar" ? "active" : ""}
              onClick={() => switchLanguage("ar")}
              disabled={busy}
            >
              {t("languageArabic")}
            </button>
          </div>
          <button type="button" className="btn ghost" onClick={regen} disabled={busy}>
            {t("regenerateData")}
          </button>
        </div>
      </header>

      {coordinatesOutsideDemo ? (
        <div className="banner warning demo-coordinates-warning" role="alert">
          {t("coordinatesOutsideDemoMessage")}
        </div>
      ) : null}
      {error ? <div className="banner error" role="alert">{error}</div> : null}

      <section className="kpi-strip" aria-label="Portfolio summary">
        {loading || !summary ? (
          <div className="kpi-loading muted">{t("loadingPortfolio")}</div>
        ) : (
          <>
            <div className="kpi-card kpi-card--total">
              <span className="kpi-label">{t("syntheticAssets")}</span>
              <strong className="kpi-value">{infrastructure.length}</strong>
              <span className="kpi-hint muted small">{t("mappedUtilityLayer")}</span>
            </div>
            <div className="kpi-card kpi-card--high">
              <span className="kpi-label">{t("projects")}</span>
              <strong className="kpi-value">{projects.length}</strong>
              <span className="kpi-hint muted small">{t("syntheticWorkZones")}</span>
            </div>
            <div className="kpi-card kpi-card--med">
              <span className="kpi-label">{t("incidents")}</span>
              <strong className="kpi-value">{incidents.length}</strong>
              <span className="kpi-hint muted small">{t("historicalContext")}</span>
            </div>
            <div
              className={`kpi-card kpi-card--status risk-tone--${status.tone}`}
              style={statusStyle}
            >
              <span className="kpi-label">{t("locationStatus")}</span>
              <strong className="kpi-value">{locationStatusLabel}</strong>
              <span className="kpi-hint muted small">{t("mediumHighRisky")}</span>
            </div>
          </>
        )}
      </section>

      <WorkflowStrip hasAnalysis={hasAnalysis} busy={busy} t={t} />
      <AnalysisPipeline active={busy} stepIndex={pipelineStepIndex} t={t} />

      <div className="layout layout--manual">
        <main className="main">
          <section className="intelligence-strip" aria-label="Digital twin intelligence">
            <div className="intel-card">
              <span className="intel-label">{t("highestFocus")}</span>
              <strong>{intelligence.highestRisk}</strong>
              <span className="muted small">{t("currentManualAnalysis")}</span>
            </div>
            <div className="intel-card">
              <span className="intel-label">{t("hotspotDensity")}</span>
              <strong>{intelligence.hotspotDensity}</strong>
              <span className="muted small">{t("incidentsPerRequest")}</span>
            </div>
            <div className="intel-card">
              <span className="intel-label">{t("activeOverlaps")}</span>
              <strong>{intelligence.activeOverlaps}</strong>
              <span className="muted small">{t("currentProjectOverlaps")}</span>
            </div>
            <div className="intel-card">
              <span className="intel-label">{t("dominantUtilityType")}</span>
              <strong>{intelligence.topInfraType}</strong>
              <span className="muted small">{t("mostRepresentedAsset")}</span>
            </div>
          </section>

          <section className="section-block">
            <div className="section-header">
              <h2 className="section-title">{t("locationAnalysisWorkspace")}</h2>
              <p className="section-desc muted small">{t("workspaceHint")}</p>
            </div>
            <p className="poc-transparency-note">
              {t("pocTransparencyNote")}
            </p>
            <div className="grid-two grid-two--workspace">
              <div className="detail-stack">
                <LocationForm
                  form={form}
                  setForm={setForm}
                  onSubmit={runAnalysis}
                  busy={busy}
                  t={t}
                  highlightCoordsOutsideDemo={coordinatesOutsideDemo}
                  coordShakeNonce={coordShakeNonce}
                  onCoordinateFieldChange={() => setCoordinatesOutsideDemo(false)}
                />
                <AiCopilotPanel analysis={analysisForCopilot} t={t} />
                <RiskCard risk={risk} t={t} />
              </div>
              <MapView
                submittedInput={lastAnalyzedInput}
                analysis={analysis}
                infrastructure={infrastructure}
                projects={projects}
                layerFilters={layerFilters}
                setLayerFilters={setLayerFilters}
                busy={busy}
                language={language}
                t={t}
              />
              <div className="detail-stack">
                <OverlapLists analysis={analysis} language={language} t={t} />
                <TimelineView analysis={analysis} language={language} t={t} />
              </div>
            </div>
          </section>

          <section className="section-block section-block--ops">
            <div className="section-header">
              <h2 className="section-title">{t("liveEventStream")}</h2>
              <p className="section-desc muted small">{t("liveEventSubtitle")}</p>
            </div>
            <div className="grid-two grid-two--ops">
              <OperationalEventStream analysis={analysis} events={events} t={t} />
              <RiskTimelineSimulation analysis={analysis} timeline={timeline} onSimulate={simulateTimeline} t={t} />
              {previousAnalysis && analysis ? <WhatChangedPanel previousAnalysis={previousAnalysis} analysis={analysis} t={t} /> : null}
            </div>
          </section>

          <section className="section-block section-block--analysis">
            <div className="section-header">
              <h2 className="section-title">{t("analysisOutput")}</h2>
              <p className="section-desc muted small">
                {t("analysisOutputHint")}
              </p>
            </div>
            <div className="grid-two grid-two--analysis">
              <ExplanationPanel text={analysis?.explanation} t={t} />
              <RecommendationPanel items={analysis?.recommendations} t={t} />
            </div>
          </section>
        </main>
      </div>
    </div>
  );
}
