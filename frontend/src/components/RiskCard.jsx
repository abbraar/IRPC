import FactorChart from "./FactorChart.jsx";
import { riskLabel } from "../i18n.js";
import { getRiskTheme, riskCssVars } from "../riskTheme.js";

const factorLabelKey = {
  geometry_depth: "depth",
  geometry_radius: "workRadius",
  utility_proximity: "infrastructure",
  project_site_pressure: "projects",
  schedule_overlap: "temporal",
  overlapping_projects: "spatialTemporal",
  incident_history: "incidents",
  manual_infrastructure_overlap: "infrastructure",
  manual_depth: "depth",
  manual_radius: "workRadius",
  manual_nearby_assets: "syntheticAssets",
  manual_incidents: "incidents",
  manual_project_spatial: "projects",
  manual_project_temporal: "temporal",
  manual_combined_project_conflict: "spatialTemporal",
};

const categoryKey = {
  Geometry: "depth",
  "Buried utilities": "infrastructure",
  Coordination: "projects",
  History: "incidents",
};

export default function RiskCard({ risk, t = (key) => key }) {
  if (!risk) {
    return (
      <div className="card risk-card risk-card--empty">
        <div className="card-heading">
          <span className="card-icon card-icon--gauge" aria-hidden />
          <div>
            <h3>{t("riskAssessment")}</h3>
            <p className="card-subtitle muted small">{t("riskScore")} (0-100)</p>
          </div>
        </div>
        <div className="empty-state empty-state--compact">
          <p className="empty-state-title">{t("awaitingAnalysis")}</p>
          <p className="muted small">{t("explanationHint")}</p>
        </div>
      </div>
    );
  }

  const level = risk.risk_level || "Low";
  const meta = getRiskTheme(level);
  const levelText = risk.risk_level_label || riskLabel(level, t);
  const pct = Math.min(100, Math.max(0, risk.risk_score));
  const gaugeStyle = {
    ...riskCssVars(level),
    "--risk-pct": `${pct}%`,
  };

  return (
    <div
      className={`card risk-card risk-card--${meta.tone}`}
      style={gaugeStyle}
    >
      <div className="card-heading">
        <span className="card-icon card-icon--gauge" aria-hidden />
        <div className="risk-card-heading-text">
          <h3>{t("riskAssessment")}</h3>
          <p className="card-subtitle muted small">{t("riskScore")} (0-100)</p>
        </div>
        <span className={`risk-pill risk-pill--${level.toLowerCase()}`}>{levelText}</span>
      </div>

      <div className="risk-score-grid">
        <div className="risk-radial-wrap" aria-label={`Risk score ${risk.risk_score} out of 100`}>
          <div className="risk-radial">
            <div className="risk-radial-inner">
              <span key={risk.risk_score} className="risk-score-num">{risk.risk_score}</span>
              <span className="risk-score-denom">/100</span>
            </div>
          </div>
        </div>
        <div className="risk-score-block">
          <div className="risk-score-main" style={{ color: meta.color }}>
            <span className="risk-score-label">{levelText}</span>
          </div>
          <div className="meter risk-meter" aria-hidden>
            <div className="meter-fill" style={{ width: `${pct}%`, background: meta.color }} />
          </div>
          <div className="risk-meter-labels muted small">
            <span>0</span>
            <span>{t("lowRisk")} 30</span>
            <span>{t("mediumRisk")} 70</span>
            <span>100</span>
          </div>
        </div>
      </div>

      <div className="confidence-block">
        <div className="confidence-row">
          <span className="confidence-label">{t("confidenceIndex")}</span>
          <span className="confidence-value">{Math.round((risk.confidence_score ?? 0) * 100)}%</span>
        </div>
        <div className="confidence-bar" aria-hidden>
          <div
            className="confidence-bar-fill"
            style={{ width: `${Math.round((risk.confidence_score ?? 0) * 100)}%` }}
          />
        </div>
      </div>

      {risk.confidence_rationale ? (
        <div className="confidence-rationale-wrap">
          <p className="confidence-rationale-label small">{t("confidenceRationale")}</p>
          <p className="confidence-rationale muted small">{risk.confidence_rationale}</p>
        </div>
      ) : null}

      {Array.isArray(risk.contributing_factors) && risk.contributing_factors.length > 0 ? (
        <div className="factor-mini">
          <h4 className="factor-mini-title">{t("primaryDrivers")}</h4>
          <ul className="factor-mini-list">
            {[...risk.contributing_factors]
              .sort((a, b) => (b.weight_contribution ?? 0) - (a.weight_contribution ?? 0))
              .slice(0, 4)
              .map((f) => (
                <li key={f.factor}>
                  <div className="factor-row-head">
                    <span className="factor-cat">{t(categoryKey[f.category] || f.category)}</span>
                    <span className="factor-weight muted small">
                      {Number(f.weight_contribution).toFixed(1)} pts
                      {f.pct_of_composite != null ? ` · ${f.pct_of_composite}%` : ""}
                    </span>
                  </div>
                  <span className="factor-name">{t(factorLabelKey[f.factor] || f.display_name)}</span>
                </li>
              ))}
          </ul>
          <FactorChart factors={risk.contributing_factors} t={t} />
        </div>
      ) : null}
    </div>
  );
}
