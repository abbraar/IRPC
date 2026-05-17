"""Structured, analyst-style narrative from deterministic rules (no LLM)."""

from models import DetectedConflicts, ExcavationRequest, RiskResult


def _bullet_line(text: str) -> str:
    return f"• {text}"


def build_explanation(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    risk: RiskResult,
) -> str:
    infra_s = [c for c in conflicts.spatial if c.kind == "infrastructure"]
    high_infra = [c for c in infra_s if c.severity == "High"]
    med_infra = [c for c in infra_s if c.severity == "Medium"]
    low_infra = [c for c in infra_s if c.severity == "Low"]
    proj_s = [c for c in conflicts.spatial if c.kind == "project_site"]
    overlaps = conflicts.temporal

    sorted_factors = sorted(
        risk.contributing_factors,
        key=lambda f: f.weight_contribution,
        reverse=True,
    )
    top_lines = []
    for f in sorted_factors[:4]:
        if f.weight_contribution <= 0.05:
            continue
        top_lines.append(
            f"{f.display_name}: {f.weight_contribution:.1f} index pts "
            f"({f.pct_of_composite:.1f}% of the uncapped composite). {f.detail}"
        )

    lines: list[str] = []

    lines.append("ASSESSMENT SUMMARY")
    lines.append(
        f"Excavation request {excavation.request_id} ({excavation.excavation_type}, "
        f"{excavation.contractor_name}) is rated {risk.risk_level.upper()} on the 0–100 rule index "
        f"(score {risk.risk_score:.1f}). Analyst confidence in this automated pass is "
        f"{risk.confidence_score:.0%}; see the confidence rationale on the risk card."
    )

    lines.append("")
    lines.append("CONFLICT REGISTER (DISCRETE FLAGS)")
    if not infra_s and not proj_s and not overlaps:
        lines.append(_bullet_line("No spatial or temporal conflicts exceeded demo detection thresholds."))
    else:
        if infra_s:
            lines.append(
                _bullet_line(
                    f"Buried utilities: {len(infra_s)} proximity alert(s); "
                    f"{len(high_infra)} high, {len(med_infra)} medium, {len(low_infra)} low severity."
                )
            )
            if high_infra:
                n = min(high_infra, key=lambda x: x.distance_meters)
                lines.append(
                    _bullet_line(
                        f"Tightest high-severity utility clearance: {n.distance_meters:.1f}m to {n.target_name}."
                    )
                )
        if proj_s:
            closest = min(proj_s, key=lambda x: x.distance_meters)
            lines.append(
                _bullet_line(
                    f"Third-party work sites: {len(proj_s)} inside coordination radius; "
                    f"closest footprint {closest.distance_meters:.1f}m ({closest.target_name})."
                )
            )
        if overlaps:
            max_ov = max(overlaps, key=lambda t: t.overlap_days)
            lines.append(
                _bullet_line(
                    f"Schedule: {len(overlaps)} overlapping project calendar window(s); "
                    f"largest overlap {max_ov.overlap_days} calendar days ({max_ov.project_name})."
                )
            )

    lines.append("")
    lines.append("PRIMARY CONTRIBUTORS TO THE COMPOSITE INDEX")
    if top_lines:
        for t in top_lines:
            lines.append(_bullet_line(t))
    else:
        lines.append(_bullet_line("All line items are below the reporting noise floor for this run."))

    lines.append("")
    lines.append("ANALYST GUIDANCE")
    lines.append(
        _bullet_line(
            "This output is a rule-based desk screening on synthetic coordinates. "
            "Field locate, permits, and owner as-builts remain authoritative regardless of index value."
        )
    )

    return "\n".join(lines)
