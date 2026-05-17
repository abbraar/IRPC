export const riskTheme = {
  low: {
    tone: "low",
    level: "Low",
    color: "var(--risk-low)",
    colorValue: "#34d399",
    bg: "var(--risk-low-bg)",
    border: "var(--risk-low-border)",
    glow: "#34d39944",
  },
  medium: {
    tone: "medium",
    level: "Medium",
    color: "var(--risk-med)",
    colorValue: "#fbbf24",
    bg: "var(--risk-med-bg)",
    border: "var(--risk-med-border)",
    glow: "#fbbf2444",
  },
  high: {
    tone: "high",
    level: "High",
    color: "var(--risk-high)",
    colorValue: "#f87171",
    bg: "var(--risk-high-bg)",
    border: "var(--risk-high-border)",
    glow: "#f8717144",
  },
};

export function getRiskTone(level) {
  const value = String(level || "Low").toLowerCase();
  if (value === "high" || value.includes("critical")) return "high";
  if (value === "medium" || value.includes("elevated")) return "medium";
  return "low";
}

export function getRiskTheme(level) {
  return riskTheme[getRiskTone(level)];
}

export function riskCssVars(level) {
  const theme = getRiskTheme(level);
  return {
    "--risk-accent": theme.color,
    "--risk-accent-bg": theme.bg,
    "--risk-accent-border": theme.border,
    "--risk-glow": theme.glow,
  };
}
