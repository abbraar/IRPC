"""Cause-aware recommendations derived from risk line items + discrete conflicts (rule-based POC)."""

from models import ContributingFactor, RecommendationItem, RiskResult, DetectedConflicts


def _factor_map(factors: list[ContributingFactor]) -> dict[str, float]:
    return {f.factor: f.weight_contribution for f in factors}


def recommend(risk: RiskResult, conflicts: DetectedConflicts) -> list[RecommendationItem]:
    recs: list[RecommendationItem] = []
    fm = _factor_map(risk.contributing_factors)

    high_infra = sum(1 for c in conflicts.spatial if c.kind == "infrastructure" and c.severity == "High")
    med_infra = sum(1 for c in conflicts.spatial if c.kind == "infrastructure" and c.severity == "Medium")
    high_proj = sum(1 for c in conflicts.spatial if c.kind == "project_site" and c.severity == "High")
    high_temp = sum(1 for t in conflicts.temporal if t.severity == "High")

    util_pts = fm.get("utility_proximity", 0.0)
    sched_pts = fm.get("schedule_overlap", 0.0) + fm.get("overlapping_projects", 0.0)
    site_pts = fm.get("project_site_pressure", 0.0)
    hist_pts = fm.get("incident_history", 0.0)
    geom_pts = fm.get("geometry_depth", 0.0) + fm.get("geometry_radius", 0.0)

    utility_driver = util_pts >= 14.0 or high_infra >= 1
    schedule_driver = sched_pts >= 4.0 or len(conflicts.temporal) > 0 or high_temp >= 1
    site_driver = site_pts >= 4.5 or high_proj >= 2
    history_driver = hist_pts >= 3.5
    geometry_driver = geom_pts >= 10.0

    # --- Tier 1: strong escalation ---
    if (
        risk.risk_level == "High"
        or high_infra >= 2
        or (high_infra >= 1 and high_temp >= 1)
        or high_temp >= 2
        or util_pts >= 28.0
    ):
        if utility_driver:
            recs.append(
                RecommendationItem(
                    action="Manual review required",
                    reasoning=(
                        "The buried-utility stress channel and/or high-severity proximity flags are elevated. "
                        "Hold excavation until a qualified engineer reconciles marks with owner records and "
                        "confirms cover / alignment."
                    ),
                    priority="high",
                )
            )
        else:
            recs.append(
                RecommendationItem(
                    action="Manual review required",
                    reasoning=(
                        "Composite index and/or schedule stress crossed escalation thresholds without a single "
                        "dominant utility driver - still require formal review because coordination failure modes "
                        "remain material."
                    ),
                    priority="high",
                )
            )

        if schedule_driver:
            recs.append(
                RecommendationItem(
                    action="Reschedule",
                    reasoning=(
                        "Calendar overlap with nearby crews materially increases simultaneous exposure. "
                        "Sequence work so locate, pothole, and open-cut phases are not competing for the same corridor."
                    ),
                    priority="high",
                )
            )
        elif site_driver:
            recs.append(
                RecommendationItem(
                    action="Reschedule",
                    reasoning=(
                        "Multiple active third-party footprints are inside the coordination envelope even if "
                        "calendar overlap is thin - align site access windows before mobilizing heavy equipment."
                    ),
                    priority="medium",
                )
            )

        if utility_driver or high_infra:
            recs.append(
                RecommendationItem(
                    action="Reroute",
                    reasoning=(
                        "Where design permits, shift the trench alignment or reduce the lateral work envelope to "
                        "increase horizontal clearance from the highest-severity mapped utilities."
                    ),
                    priority="medium",
                )
            )
        elif geometry_driver:
            recs.append(
                RecommendationItem(
                    action="Reroute",
                    reasoning=(
                        "Geometry-only stress is high (deep and/or wide footprint). Evaluate a shallower staging "
                        "or staged excavation to reduce lateral exposure if utilities cannot be relocated."
                    ),
                    priority="medium",
                )
            )

        return recs[:4] if len(recs) > 4 else recs

    # --- Tier 2: moderate / mixed drivers ---
    if (
        risk.risk_level == "Medium"
        or high_infra == 1
        or med_infra >= 2
        or len(conflicts.temporal) > 0
        or high_proj >= 2
        or util_pts >= 10.0
    ):
        recs.append(
            RecommendationItem(
                action="Proceed with caution",
                reasoning=(
                    "Index and/or discrete flags indicate manageable but non-trivial exposure. "
                    "Execute standard one-call / locate, pothole critical alignments, and maintain "
                    "exposed-line watch when within owner tolerance distances."
                ),
                priority="medium",
            )
        )

        if schedule_driver:
            recs.append(
                RecommendationItem(
                    action="Reschedule",
                    reasoning=(
                        "Partial date shifts or off-peak shifts can remove overlap with flagged project windows "
                        "without redesigning the excavation."
                    ),
                    priority="medium",
                )
            )
        elif site_driver and not schedule_driver:
            recs.append(
                RecommendationItem(
                    action="Reschedule",
                    reasoning=(
                        "Nearby project footprints warrant a joint site walk and agreed sequencing even when "
                        "strict calendar overlap is limited."
                    ),
                    priority="low",
                )
            )

        if utility_driver:
            recs.append(
                RecommendationItem(
                    action="Manual review required",
                    reasoning=(
                        "Utility proximity index or medium-severity alerts triggered - have asset owners confirm "
                        "depth, material, and protection before proceeding past locate."
                    ),
                    priority="medium",
                )
            )
        elif history_driver:
            recs.append(
                RecommendationItem(
                    action="Manual review required",
                    reasoning=(
                        "Historical incident stress in the corridor is non-trivial on synthetic data; "
                        "review prior strike reports and lessons learned for this alignment before cut."
                    ),
                    priority="low",
                )
            )
        else:
            recs.append(
                RecommendationItem(
                    action="Manual review required",
                    reasoning=(
                        "Targeted engineering review of the conflict list against permits is still recommended "
                        "before ground disturbance."
                    ),
                    priority="low",
                )
            )

        return recs

    # --- Tier 3: low composite ---
    recs.append(
        RecommendationItem(
            action="Proceed",
            reasoning=(
                "Under demo thresholds the composite index and discrete conflict register are subdued. "
                "Proceed under normal controls once statutory locate and permit conditions are satisfied."
            ),
            priority="low",
        )
    )
    if history_driver or geometry_driver:
        recs.append(
            RecommendationItem(
                action="Proceed with caution",
                reasoning=(
                    "Even with a low headline index, keep heightened awareness when geometry is aggressive or "
                    "local incident history suggests repeated third-party damage along the alignment."
                ),
                priority="low",
            )
        )
    else:
        recs.append(
            RecommendationItem(
                action="Proceed with caution",
                reasoning=(
                    "Synthetic data omits unmapped utilities; maintain standard verification discipline regardless "
                    "of index value."
                ),
                priority="low",
            )
        )
    return recs
