"""
Rule-based composite risk index (0–100) with explicit weight budget, line-item register,
and analyst confidence heuristic (POC — no calibration to real strike rates).
"""

from __future__ import annotations

from models import (
    ContributingFactor,
    ExcavationRequest,
    HistoricalIncident,
    InfrastructureAsset,
    Project,
    RiskResult,
    DetectedConflicts,
)
from services.conflict_detection import (
    ASSET_TYPE_STRESS,
    CRITICALITY_STRESS,
    INCIDENT_RADIUS_M,
    count_infrastructure_within,
    haversine_m,
    incident_proximity_count,
    incident_weighted_stress,
    nearby_project_density,
)

# --- Weight budget (points). Theoretical stressed maximum sums to 100 before final cap. ---
MAX_DEPTH = 10.0
MAX_RADIUS = 8.0
MAX_UTILITY = 38.0
MAX_PROJECT_SITES = 15.0
MAX_SCHEDULE = 12.0
MAX_OVERLAP_DENSITY = 9.0
MAX_INCIDENT = 8.0

UTILITY_RADIUS_M = 52.0


def _clamp_score(x: float) -> float:
    return max(0.0, min(100.0, x))


def _risk_level(score: float) -> str:
    if score <= 30:
        return "Low"
    if score <= 70:
        return "Medium"
    return "High"


def _nearest_utility_summary(excavation: ExcavationRequest, infrastructure: list[InfrastructureAsset]) -> tuple[float, str | None]:
    """Closest mapped utility (m) and one-line label for narrative factors."""
    best_d: float | None = None
    best_label: str | None = None
    for a in infrastructure:
        d = haversine_m(excavation.latitude, excavation.longitude, a.latitude, a.longitude)
        if best_d is None or d < best_d:
            best_d = d
            best_label = f"{a.type} ({a.criticality})"
    if best_d is None:
        return 9999.0, None
    return best_d, best_label


def _compute_confidence(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    infrastructure: list[InfrastructureAsset],
    incidents: list[HistoricalIncident],
    inc_count: int,
) -> tuple[float, str]:
    """
    Heuristic 0–1: higher when local records are dense and conflicts are well structured.
    Not a statistical confidence interval — documented for analysts in confidence_rationale.
    """
    n_120 = count_infrastructure_within(excavation, infrastructure, 120.0)
    n_200 = count_infrastructure_within(excavation, infrastructure, 200.0)
    n_spatial = len(conflicts.spatial)
    n_temp = len(conflicts.temporal)

    # Sub-scores 0–1
    utility_coverage = min(1.0, n_120 / 9.0)
    incident_signal = min(1.0, inc_count / 5.5) if inc_count else 0.0
    conflict_structure = min(1.0, n_spatial * 0.11 + n_temp * 0.14)
    regional_catalog = min(1.0, n_200 / 14.0)

    # Sparse catalog lowers ceiling (unknown-unknowns in POC)
    sparsity = max(0.0, 1.0 - regional_catalog)

    inner = (
        0.30 * utility_coverage
        + 0.22 * incident_signal
        + 0.28 * conflict_structure
        + 0.20 * regional_catalog
    )
    confidence = 0.40 + 0.52 * inner - 0.12 * sparsity
    confidence = max(0.42, min(0.92, round(confidence, 2)))

    if utility_coverage >= 0.55:
        u_txt = (
            "Mapped utility density within 120m is moderate to high, which improves internal consistency "
            "of the buried-asset proximity terms for this desk pass."
        )
    elif utility_coverage >= 0.28:
        u_txt = "Mapped utility density is moderate; treat strike indices as directionally useful but not exhaustive."
    else:
        u_txt = (
            "Mapped utilities are sparse near the pin; the model has less local geometry to condition on, "
            "so scores lean conservative on unknown-unknowns."
        )

    if incident_signal >= 0.45:
        i_txt = "Several weighted incidents fall inside the review radius, strengthening the historical stress channel."
    elif inc_count == 0:
        i_txt = "No incidents were recorded inside the standard review radius for this synthetic draw."
    else:
        i_txt = "Incident count is low inside the review radius; the history channel is lightly exercised."

    if conflict_structure >= 0.5:
        c_txt = "Spatial and temporal conflict objects are well populated, improving interpretability of coordination risk."
    else:
        c_txt = "Fewer discrete conflicts were flagged; cross-checks against third-party schedules are thinner."

    rationale = (
        "This value is a rule-coverage index for synthetic data - not a calibrated probability of strike or failure. "
        + u_txt
        + " "
        + i_txt
        + " "
        + c_txt
    )
    return confidence, rationale


def compute_risk(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> RiskResult:
    # --- Geometry (excavator-controlled exposure) ---
    depth_norm = min(excavation.depth / 5.0, 1.0) ** 0.92
    depth_pts = MAX_DEPTH * depth_norm

    radius_norm = min(excavation.radius_meters / 20.0, 1.0) ** 0.88
    radius_pts = MAX_RADIUS * radius_norm

    # --- Buried utilities (continuous proximity; separate from discrete conflict list) ---
    utility_pts = 0.0
    nearest_d, nearest_label = _nearest_utility_summary(excavation, infrastructure)
    for asset in infrastructure:
        d = haversine_m(
            excavation.latitude,
            excavation.longitude,
            asset.latitude,
            asset.longitude,
        )
        if d > UTILITY_RADIUS_M:
            continue
        dn = max(0.0, 1.0 - d / UTILITY_RADIUS_M)
        type_m = ASSET_TYPE_STRESS.get(asset.type, 1.0)
        crit_m = CRITICALITY_STRESS.get(asset.criticality, 1.0)
        sens = 0.42 + 0.58 * (asset.sensitivity_score / 100.0)
        # Depth alignment: trench bottom near / below asset depth increases index contribution
        strike_align = 1.0
        if excavation.depth >= asset.depth - 0.35:
            strike_align += 0.35 * min(1.0, (excavation.depth - asset.depth + 0.35) / 2.5)
        utility_pts += (dn**1.38) * type_m * crit_m * sens * strike_align * (MAX_UTILITY / 6.2)

    utility_pts = min(MAX_UTILITY, utility_pts)
    util_detail = (
        f"Aggregated proximity index within {UTILITY_RADIUS_M:.0f}m of mapped utilities "
        f"(type × criticality × sensitivity × shallow-depth alignment). "
        f"Closest recorded asset: ~{nearest_d:.1f}m ({nearest_label})."
        if nearest_label
        else f"No mapped utilities within {UTILITY_RADIUS_M:.0f}m horizontal envelope."
    )

    # --- Coordination: other project footprints (from conflict engine; not double-counted with utility index) ---
    proj_spatial = [c for c in conflicts.spatial if c.kind == "project_site"]
    site_pts = 0.0
    for c in proj_spatial:
        if c.severity == "High":
            site_pts += 5.8
        elif c.severity == "Medium":
            site_pts += 3.2
        else:
            site_pts += 1.1
    site_pts = min(MAX_PROJECT_SITES, site_pts)
    site_detail = (
        f"{len(proj_spatial)} nearby third-party work site(s) inside the coordination corridor "
        f"(severity-weighted index capped at {MAX_PROJECT_SITES:.0f} pts)."
    )

    high_temp = sum(1 for t in conflicts.temporal if t.severity == "High")
    med_temp = sum(1 for t in conflicts.temporal if t.severity == "Medium")
    overlap_day_weight = sum(t.overlap_days for t in conflicts.temporal) * 0.16
    sched_pts = min(
        MAX_SCHEDULE,
        high_temp * 3.4 + med_temp * 1.5 + overlap_day_weight + len(conflicts.temporal) * 0.9,
    )
    sched_detail = (
        f"{len(conflicts.temporal)} overlapping schedule window(s) vs third-party projects "
        f"({high_temp} high / {med_temp} medium temporal class); "
        f"combined overlap weight {overlap_day_weight:.1f} day-equivalents in rule index."
    )

    density = nearby_project_density(excavation, projects)
    dens_pts = min(MAX_OVERLAP_DENSITY, density * 1.75)
    dens_detail = (
        f"{density} concurrent project(s) within ~80m with calendar overlap on this excavation "
        f"(coordination density capped at {MAX_OVERLAP_DENSITY:.0f} pts)."
    )

    inc_count = incident_proximity_count(excavation, incidents)
    inc_stress = incident_weighted_stress(excavation, incidents)
    hist_pts = min(MAX_INCIDENT, inc_stress * 2.35 + min(inc_count, 8) * 0.45)
    hist_detail = (
        f"{inc_count} synthetic incident(s) within {INCIDENT_RADIUS_M:.0f}m; "
        f"severity-weighted proximity stress {inc_stress:.2f} → capped history contribution."
    )

    raw = depth_pts + radius_pts + utility_pts + site_pts + sched_pts + dens_pts + hist_pts
    score = _clamp_score(raw)
    level = _risk_level(score)

    factors: list[ContributingFactor] = [
        ContributingFactor(
            factor="geometry_depth",
            display_name="Excavation depth (vertical exposure)",
            category="Geometry",
            weight_contribution=round(depth_pts, 2),
            pct_of_composite=0.0,
            detail=(
                f"Trench design depth {excavation.depth}m maps to {depth_norm:.0%} of the reference "
                f"profile (normalized before applying the {MAX_DEPTH:.0f}-point geometry budget)."
            ),
        ),
        ContributingFactor(
            factor="geometry_radius",
            display_name="Work zone radius (lateral exposure)",
            category="Geometry",
            weight_contribution=round(radius_pts, 2),
            pct_of_composite=0.0,
            detail=(
                f"Declared work radius {excavation.radius_meters}m → lateral envelope index {radius_norm:.0%} "
                f"against the {MAX_RADIUS:.0f}-point lateral budget."
            ),
        ),
        ContributingFactor(
            factor="utility_proximity",
            display_name="Mapped buried utility stress",
            category="Buried utilities",
            weight_contribution=round(utility_pts, 2),
            pct_of_composite=0.0,
            detail=util_detail,
        ),
        ContributingFactor(
            factor="project_site_pressure",
            display_name="Third-party project footprint pressure",
            category="Coordination",
            weight_contribution=round(site_pts, 2),
            pct_of_composite=0.0,
            detail=site_detail,
        ),
        ContributingFactor(
            factor="schedule_overlap",
            display_name="Calendar overlap with nearby work",
            category="Coordination",
            weight_contribution=round(sched_pts, 2),
            pct_of_composite=0.0,
            detail=sched_detail,
        ),
        ContributingFactor(
            factor="overlapping_projects",
            display_name="Concurrent overlapping projects (80m)",
            category="Coordination",
            weight_contribution=round(dens_pts, 2),
            pct_of_composite=0.0,
            detail=dens_detail,
        ),
        ContributingFactor(
            factor="incident_history",
            display_name="Historical incident stress (local)",
            category="History",
            weight_contribution=round(hist_pts, 2),
            pct_of_composite=0.0,
            detail=hist_detail,
        ),
    ]

    pre_cap_total = sum(f.weight_contribution for f in factors)
    if pre_cap_total > 0:
        for f in factors:
            f.pct_of_composite = round(100.0 * f.weight_contribution / pre_cap_total, 1)
    else:
        for f in factors:
            f.pct_of_composite = 0.0

    # If composite hit the 100 cap, attach a single audit note to the largest driver line item
    if raw > 100.0 + 1e-6:
        over = raw - 100.0
        top = max(factors, key=lambda f: f.weight_contribution)
        top.detail += (
            f" Reporting note: uncapped weighted sum was {raw:.1f} before the 100-point ceiling "
            f"({over:.1f} pts suppressed)."
        )

    confidence, rationale = _compute_confidence(excavation, conflicts, infrastructure, incidents, inc_count)

    return RiskResult(
        risk_score=round(score, 1),
        risk_level=level,  # type: ignore[arg-type]
        contributing_factors=factors,
        confidence_score=confidence,
        confidence_rationale=rationale,
    )
