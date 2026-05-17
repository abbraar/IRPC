const categoryColor = {
  Geometry: "#38bdf8",
  "Buried utilities": "#fb923c",
  Coordination: "#a78bfa",
  History: "#34d399",
};

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

export default function FactorChart({ factors = [], t = (key) => key }) {
  const sorted = [...factors]
    .sort((a, b) => (b.weight_contribution ?? 0) - (a.weight_contribution ?? 0))
    .slice(0, 6);

  if (!sorted.length) {
    return null;
  }

  return (
    <div className="factor-chart">
      <div className="factor-chart-head">
        <h4>{t("contributionProfile")}</h4>
        <span className="muted small">{t("topWeightedFactors")}</span>
      </div>
      <div className="factor-bars">
        {sorted.map((f) => {
          const pct = Math.max(0, Math.min(100, Number(f.pct_of_composite ?? 0)));
          const color = categoryColor[f.category] || "var(--accent)";
          return (
            <div key={f.factor} className="factor-bar-row">
              <div className="factor-bar-meta">
                <span className="factor-bar-name">{t(factorLabelKey[f.factor] || f.display_name)}</span>
                <span className="factor-bar-value">{pct.toFixed(1)}%</span>
              </div>
              <div className="factor-track" aria-hidden>
                <div
                  className="factor-track-fill"
                  style={{ width: `${pct}%`, "--factor-color": color }}
                />
              </div>
              <span className="factor-bar-category small" style={{ color }}>
                {t(categoryKey[f.category] || f.category)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
