import { priorityLabel, riskLabel } from "../i18n.js";

function priorityTone(priority) {
  const p = String(priority || "").toLowerCase();
  if (p === "high") return "copilot-priority--high";
  if (p === "medium") return "copilot-priority--medium";
  return "copilot-priority--low";
}

function confidenceText(value, t) {
  if (value >= 0.78) return t("highConfidence");
  if (value >= 0.58) return t("mediumConfidence");
  return t("lowConfidence");
}

export default function AiCopilotPanel({ analysis, t = (key) => key }) {
  const risk = analysis?.risk;
  const primaryRecommendation = analysis?.recommendations?.[0];

  return (
    <div className="card copilot-card">
      <div className="copilot-orb" aria-hidden />
      <div className="card-heading copilot-heading">
        <span className="card-icon card-icon--ai" aria-hidden />
        <div>
          <h3>{t("aiAnalystAssistant")}</h3>
          <p className="card-subtitle muted small">{t("assistantSubtitle")}</p>
        </div>
      </div>

      {!analysis ? (
        <div className="empty-state empty-state--compact">
          <p className="empty-state-title">{t("assistantStandby")}</p>
          <p className="muted small">{t("assistantHint")}</p>
        </div>
      ) : (
        <div className="copilot-content">
          <div className="copilot-brief">
            <span className={`copilot-risk copilot-risk--${risk.risk_level.toLowerCase()}`}>
              {risk.risk_level_label || riskLabel(risk.risk_level, t)} · {risk.risk_score}/100
            </span>
          </div>

          <div className="copilot-confidence">
            <span className="muted small">{t("confidenceInterpretation")}</span>
            <strong>{confidenceText(risk.confidence_score, t)}</strong>
          </div>

          {primaryRecommendation ? (
            <div className="copilot-next">
              <span className="muted small">{t("recommendedNextAction")}</span>
              <div className="copilot-next-head">
                <strong>{primaryRecommendation.action}</strong>
                <span className={`copilot-priority ${priorityTone(primaryRecommendation.priority)}`}>
                  {priorityLabel(primaryRecommendation.priority, t)}
                </span>
              </div>
              <p>{primaryRecommendation.reasoning}</p>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
