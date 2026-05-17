import { useState } from "react";

function parseExplanationLines(text) {
  const lines = text.split("\n");
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();
    if (!trimmed) {
      i += 1;
      continue;
    }
    const isSectionHeader =
      (trimmed === trimmed.toUpperCase() &&
        trimmed.length > 4 &&
        !trimmed.startsWith("•") &&
        /^[A-Z0-9 \-()]+$/.test(trimmed)) ||
      ["ملخص التقييم", "سجل التعارضات", "إرشادات المحلل"].includes(trimmed);
    if (isSectionHeader) {
      blocks.push({ type: "h", key: `h-${i}`, text: trimmed });
      i += 1;
      continue;
    }
    if (trimmed.startsWith("•") || trimmed.startsWith("-")) {
      blocks.push({ type: "bullet", key: `b-${i}`, text: trimmed.replace(/^[•-]\s*/, "") });
      i += 1;
      continue;
    }
    blocks.push({ type: "p", key: `p-${i}`, text: trimmed });
    i += 1;
  }
  return blocks;
}

function groupBlocks(blocks) {
  const sections = [];
  let current = null;
  blocks.forEach((block) => {
    if (block.type === "h") {
      current = { title: block.text, blocks: [] };
      sections.push(current);
    } else if (current) {
      current.blocks.push(block);
    } else {
      sections.push({ title: "SUMMARY", blocks: [block] });
    }
  });
  return sections;
}

function sectionIcon(title) {
  if (title.includes("CONFLICT")) return "!";
  if (title.includes("تعارض")) return "!";
  if (title.includes("CONTRIBUTOR")) return "#";
  if (title.includes("GUIDANCE")) return ">";
  if (title.includes("إرشادات")) return ">";
  return "AI";
}

export default function ExplanationPanel({ text, t = (key) => key }) {
  const [collapsed, setCollapsed] = useState(() => new Set());
  const sections = text ? groupBlocks(parseExplanationLines(text)) : [];
  const toggle = (title) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(title)) next.delete(title);
      else next.add(title);
      return next;
    });
  };

  return (
    <div className="card explanation-card card-accent">
      <div className="card-heading">
        <span className="card-icon card-icon--doc" aria-hidden />
        <div>
          <h3>{t("analystExplanation")}</h3>
          <p className="card-subtitle muted small">{t("explanationSubtitle")}</p>
        </div>
      </div>
      {!text ? (
        <div className="empty-state">
          <p className="empty-state-title">{t("awaitingAnalysis")}</p>
          <p className="muted small">{t("explanationHint")}</p>
        </div>
      ) : (
        <div className="explanation-body">
          {sections.map((section, idx) => {
            const isCollapsed = collapsed.has(section.title);
            return (
              <section key={`${section.title}-${idx}`} className="explanation-section-card">
                <button
                  type="button"
                  className="explanation-section-toggle"
                  onClick={() => toggle(section.title)}
                >
                  <span className="explanation-section-icon" aria-hidden>
                    {sectionIcon(section.title)}
                  </span>
                  <span>{section.title}</span>
                  <span className="explanation-chevron">{isCollapsed ? "+" : "-"}</span>
                </button>
                {!isCollapsed ? (
                  <div className="explanation-section-content">
                    {section.blocks.map((b) => {
                      if (b.type === "bullet") {
                        return (
                          <p key={b.key} className="explanation-bullet">
                            <span className="bullet-dot" aria-hidden>
                              ·
                            </span>
                            {b.text}
                          </p>
                        );
                      }
                      return (
                        <p key={b.key} className="explanation-para">
                          {b.text}
                        </p>
                      );
                    })}
                  </div>
                ) : null}
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
