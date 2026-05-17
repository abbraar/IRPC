import { useState } from "react";
import { priorityLabel } from "../i18n.js";

const actionTone = {
  "Manual review required": "rec-tone--review",
  "Manual engineering review required": "rec-tone--review",
  "يلزم مراجعة هندسية يدوية": "rec-tone--review",
  Reschedule: "rec-tone--schedule",
  "Reschedule work window": "rec-tone--schedule",
  "إعادة جدولة فترة العمل": "rec-tone--schedule",
  Reroute: "rec-tone--reroute",
  "Reroute excavation area": "rec-tone--reroute",
  "تغيير مسار منطقة الحفر": "rec-tone--reroute",
  "Reduce work radius": "rec-tone--caution",
  "تقليل نطاق العمل": "rec-tone--caution",
  "Adjust excavation depth": "rec-tone--caution",
  "تعديل عمق الحفر": "rec-tone--caution",
  "Proceed with caution": "rec-tone--caution",
  "المتابعة بحذر": "rec-tone--caution",
  Proceed: "rec-tone--proceed",
  "المتابعة": "rec-tone--proceed",
};

const actionIcon = {
  "Manual review required": "!",
  "Manual engineering review required": "!",
  "يلزم مراجعة هندسية يدوية": "!",
  Reschedule: "R",
  "Reschedule work window": "R",
  "إعادة جدولة فترة العمل": "R",
  Reroute: ">",
  "Reroute excavation area": ">",
  "تغيير مسار منطقة الحفر": ">",
  "Reduce work radius": "-",
  "تقليل نطاق العمل": "-",
  "Adjust excavation depth": "D",
  "تعديل عمق الحفر": "D",
  "Proceed with caution": "?",
  "المتابعة بحذر": "?",
  Proceed: "OK",
  "المتابعة": "OK",
};

export default function RecommendationPanel({ items, t = (key) => key }) {
  const [openItems, setOpenItems] = useState(() => new Set([0]));
  const toggle = (idx) => {
    setOpenItems((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  return (
    <div className="card rec-card card-accent">
      <div className="card-heading">
        <span className="card-icon card-icon--list" aria-hidden />
        <div>
          <h3>{t("recommendations")}</h3>
          <p className="card-subtitle muted small">{t("recommendationsSubtitle")}</p>
        </div>
      </div>
      {!items?.length ? (
        <div className="empty-state">
          <p className="empty-state-title">{t("awaitingAnalysis")}</p>
          <p className="muted small">{t("recommendationsHint")}</p>
        </div>
      ) : (
        <ul className="rec-list">
          {items.map((r, idx) => {
            const tone = actionTone[r.action] || "rec-tone--default";
            const isOpen = openItems.has(idx);
            return (
              <li key={`${r.action}-${idx}`} className={`rec-item ${tone}`}>
                <button type="button" className="rec-head rec-toggle" onClick={() => toggle(idx)}>
                  <span className="rec-action-wrap">
                    <span className="rec-icon" aria-hidden>
                      {actionIcon[r.action] || "•"}
                    </span>
                    <strong className="rec-action">{r.action}</strong>
                  </span>
                  <span className={`prio prio-${r.priority}`}>{priorityLabel(r.priority, t)}</span>
                </button>
                {isOpen ? <p className="rec-reason">{r.reasoning}</p> : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
