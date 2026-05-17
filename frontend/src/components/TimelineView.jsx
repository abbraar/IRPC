import { getProjectLabel, getSeverityLabel } from "../i18n.js";

function toDate(value) {
  return value ? new Date(`${value}T00:00:00`) : null;
}

function daysBetween(a, b) {
  return Math.round((b.getTime() - a.getTime()) / 86400000);
}

function severityClass(value) {
  return `timeline-severity--${String(value || "Low").toLowerCase()}`;
}

export default function TimelineView({ analysis, excavation, temporal = [], projects = [], language = "en", t = (key) => key }) {
  const input = analysis?.input ?? excavation;
  const temporalRows = analysis?.temporal_overlaps ?? temporal;
  const projectRows = analysis?.context_projects ?? projects;

  if (!input) {
    return (
      <div className="card timeline-card">
        <div className="card-heading">
          <span className="card-icon card-icon--timeline" aria-hidden />
          <div>
            <h3>{t("scheduleIntelligence")}</h3>
            <p className="card-subtitle muted small">{t("scheduleIntelligenceSubtitle")}</p>
          </div>
        </div>
        <div className="empty-state empty-state--compact">
          <p className="empty-state-title">{t("awaitingAnalysis")}</p>
        </div>
      </div>
    );
  }

  const excavationStart = toDate(input.start_date);
  const excavationEnd = toDate(input.end_date);
  const conflictRows = temporalRows.map((row) => ({
    ...row,
    project: projectRows.find((p) => p.project_id === row.project_id),
  }));
  const dateCandidates = [
    excavationStart,
    excavationEnd,
    ...conflictRows.flatMap((r) => [toDate(r.start_date || r.project?.start_date), toDate(r.end_date || r.project?.end_date)]),
  ].filter(Boolean);
  const minDate = new Date(Math.min(...dateCandidates.map((d) => d.getTime())));
  const maxDate = new Date(Math.max(...dateCandidates.map((d) => d.getTime())));
  const span = Math.max(1, daysBetween(minDate, maxDate) + 1);

  const barStyle = (startValue, endValue) => {
    const start = toDate(startValue) || excavationStart;
    const end = toDate(endValue) || excavationEnd;
    const left = Math.max(0, (daysBetween(minDate, start) / span) * 100);
    const width = Math.max(3, ((daysBetween(start, end) + 1) / span) * 100);
    return { left: `${left}%`, width: `${Math.min(100 - left, width)}%` };
  };

  return (
    <div className="card timeline-card">
      <div className="card-heading">
        <span className="card-icon card-icon--timeline" aria-hidden />
        <div>
          <h3>{t("scheduleIntelligence")}</h3>
          <p className="card-subtitle muted small">
            {conflictRows.length} {conflictRows.length === 1 ? t("item") : t("items")} · {t("scheduleIntelligenceSubtitle")}
          </p>
        </div>
      </div>

      <div className="timeline-axis">
        <span>{minDate.toISOString().slice(0, 10)}</span>
        <span>{maxDate.toISOString().slice(0, 10)}</span>
      </div>

      <div className="timeline-row timeline-row--exc">
        <div className="timeline-label">
          <strong>{t("submittedExcavationSite")}</strong>
          <span className="muted small">{t("scheduleWindow")}</span>
        </div>
        <div className="timeline-track">
          <span className="timeline-bar timeline-bar--exc" style={barStyle(input.start_date, input.end_date)} />
        </div>
      </div>

      {conflictRows.length === 0 ? (
        <p className="timeline-empty muted small">{t("noTemporalOverlap")}</p>
      ) : (
        conflictRows.slice(0, 5).map((row) => (
          <div key={row.project_id} className="timeline-row">
            <div className="timeline-label">
              <strong>{getProjectLabel(row.name || row.project_name, language)}</strong>
              <span className={`timeline-severity ${severityClass(row.severity)}`}>
                {getSeverityLabel(row.severity, language)} · {row.overlap_days} {t("dOverlap")}
              </span>
            </div>
            <div className="timeline-track">
              <span
                className={`timeline-bar timeline-bar--project ${severityClass(row.severity)}`}
                style={barStyle(row.start_date || row.project?.start_date, row.end_date || row.project?.end_date)}
              />
            </div>
          </div>
        ))
      )}
    </div>
  );
}
