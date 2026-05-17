export default function ConflictList({ conflicts }) {
  if (!conflicts) {
    return (
      <div className="card conflict-card">
        <div className="card-heading">
          <span className="card-icon card-icon--alert" aria-hidden />
          <div>
            <h3>Conflict register</h3>
            <p className="card-subtitle muted small">Spatial and temporal flags from the engine.</p>
          </div>
        </div>
        <div className="empty-state empty-state--compact">
          <p className="empty-state-title">No analysis yet</p>
          <p className="muted small">Run analysis to populate conflicts.</p>
        </div>
      </div>
    );
  }

  const spatial = conflicts.spatial ?? [];
  const temporal = conflicts.temporal ?? [];

  return (
    <div className="card conflict-card">
      <div className="card-heading">
        <span className="card-icon card-icon--alert" aria-hidden />
        <div>
          <h3>Conflict register</h3>
          <p className="card-subtitle muted small">Spatial and temporal flags from the engine.</p>
        </div>
      </div>

      <div className="conflict-section">
        <div className="conflict-section-head">
          <h4>Spatial</h4>
          <span className="chip chip--neutral">{spatial.length} item{spatial.length !== 1 ? "s" : ""}</span>
        </div>
        {spatial.length === 0 ? (
          <p className="muted small conflict-empty">No spatial conflicts under demo thresholds.</p>
        ) : (
          <ul className="conflict-list">
            {spatial.map((c) => (
              <li key={`${c.kind}-${c.target_id}`}>
                <span className={`sev sev-${c.severity.toLowerCase()}`}>{c.severity}</span>
                <span className="conflict-body">
                  <strong>{c.target_name}</strong>
                  <span className="muted small">
                    {c.distance_meters} m · {c.kind.replace("_", " ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className="conflict-section conflict-section--border">
        <div className="conflict-section-head">
          <h4>Temporal</h4>
          <span className="chip chip--neutral">{temporal.length} item{temporal.length !== 1 ? "s" : ""}</span>
        </div>
        {temporal.length === 0 ? (
          <p className="muted small conflict-empty">No schedule overlaps flagged.</p>
        ) : (
          <ul className="conflict-list">
            {temporal.map((t) => (
              <li key={t.project_id}>
                <span className={`sev sev-${t.severity.toLowerCase()}`}>{t.severity}</span>
                <span className="conflict-body">
                  <strong>{t.project_name}</strong>
                  <span className="muted small">
                    {t.overlap_days} d overlap · {t.kind.replace("_", " ")}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
