export default function AnalysisPipeline({ active, stepIndex = 0, t = (key) => key }) {
  if (!active) return null;
  const defaultSteps = [
    t("stepValidatingWgs84"),
    t("stepGeneratingContext"),
    t("stepCheckingInfrastructure"),
    t("stepDetectingProjectSchedule"),
    t("stepCalculatingRisk"),
    t("stepGeneratingExplanationRecommendations"),
  ];

  return (
    <div className="pipeline-panel" role="status" aria-live="polite">
      <div className="pipeline-core">
        <span className="pipeline-spinner" aria-hidden />
        <div>
          <strong>{t("pipelineRunning")}</strong>
          <p className="muted small">{t("pipelineSubtitle")}</p>
        </div>
      </div>
      <div className="pipeline-steps">
        {defaultSteps.map((step, idx) => (
          <span
            key={step}
            className={`pipeline-step ${idx === stepIndex ? "pipeline-step--current" : ""}`}
            style={{ "--step-delay": `${idx * 0.18}s` }}
          >
            {step}...
          </span>
        ))}
      </div>
    </div>
  );
}
