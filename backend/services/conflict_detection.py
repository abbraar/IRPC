"""
Conflict detection: spatial (Haversine) + temporal overlap.

Severity uses distance bands, asset type, criticality, and a shallow depth-intersection
heuristic (POC — replace with as-built geometry when real data exists).
"""

from datetime import date
from math import asin, cos, radians, sin, sqrt

from models import (
    ExcavationRequest,
    HistoricalIncident,
    InfrastructureAsset,
    Project,
    SpatialConflict,
    TemporalConflict,
    DetectedConflicts,
)

EARTH_RADIUS_M = 6371000.0

NEAR_INFRASTRUCTURE_M = 25.0
CLOSE_INFRASTRUCTURE_M = 12.0

NEAR_PROJECT_M = 40.0
CLOSE_PROJECT_M = 20.0

INCIDENT_RADIUS_M = 150.0

# Higher = more consequence if struck (rule-based POC weights)
ASSET_TYPE_STRESS: dict[str, float] = {
    "Gas Pipeline": 1.38,
    "Electrical Cable": 1.22,
    "Water Pipe": 1.0,
    "Telecom Line": 0.86,
}

CRITICALITY_STRESS: dict[str, float] = {"Low": 0.55, "Medium": 1.0, "High": 1.42}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters between two WGS84 points."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlamb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlamb / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return EARTH_RADIUS_M * c


def _excavation_calendar_days(exc: ExcavationRequest) -> int:
    return max(1, (exc.end_date - exc.start_date).days + 1)


def _infra_interaction_index(
    distance_m: float,
    criticality: str,
    asset_type: str,
    exc_depth: float,
    asset_depth: float,
    radius_m: float,
) -> float:
    """
    0–100 internal score: combines map distance, type/criticality stress, and a coarse
    vertical alignment proxy (excavation bottom vs asset depth).
    """
    influence = radius_m + 2.5
    outer = NEAR_INFRASTRUCTURE_M + influence
    if distance_m > outer:
        return 0.0
    # Horizontal proximity: 100 at d≈0, decays to 0 at outer envelope
    d_norm = max(0.0, 1.0 - (distance_m / max(outer, 1e-6)))
    horiz = 100.0 * (d_norm**1.25)

    type_m = ASSET_TYPE_STRESS.get(asset_type, 1.0)
    crit_m = CRITICALITY_STRESS.get(criticality, 1.0)
    # Vertical: if trench is likely to reach asset elevation, increase index
    depth_delta = exc_depth - asset_depth
    if depth_delta >= -0.4:
        vertical = 55.0 + 25.0 * min(1.0, max(0.0, depth_delta / 3.0))
    elif depth_delta >= -1.2:
        vertical = 28.0
    else:
        vertical = 10.0
    # Far horizontally → damp vertical concern
    vertical *= (0.35 + 0.65 * d_norm)

    raw = horiz * 0.62 + (type_m * crit_m * 18.0) * d_norm + vertical * 0.28
    return max(0.0, min(100.0, raw))


def _infra_severity_from_index(idx: float) -> str:
    if idx >= 68.0:
        return "High"
    if idx >= 38.0:
        return "Medium"
    return "Low"


def _project_spatial_severity(distance_m: float, status: str) -> str:
    active = (status or "").strip().lower() == "active"
    close = CLOSE_PROJECT_M - (4.0 if active else 0.0)
    near = NEAR_PROJECT_M - (3.0 if active else 0.0)
    if distance_m <= close:
        return "High"
    if distance_m <= near:
        return "Medium"
    return "Low"


def _overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return 0
    return (end - start).days + 1


def _temporal_severity(overlap_days: int, exc: ExcavationRequest) -> str:
    """Overlap length vs excavation duration + absolute days (dual axis for POC)."""
    exc_days = _excavation_calendar_days(exc)
    ratio = overlap_days / float(exc_days)
    if overlap_days >= 22 or ratio >= 0.82:
        return "High"
    if overlap_days >= 6 or ratio >= 0.28:
        return "Medium"
    return "Low"


def detect_conflicts(
    excavation: ExcavationRequest,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
) -> DetectedConflicts:
    spatial: list[SpatialConflict] = []
    temporal: list[TemporalConflict] = []

    for asset in infrastructure:
        d = haversine_m(
            excavation.latitude,
            excavation.longitude,
            asset.latitude,
            asset.longitude,
        )
        influence = excavation.radius_meters + asset.influence_radius
        if d <= influence:
            idx = _infra_interaction_index(
                d,
                asset.criticality,
                asset.type,
                excavation.depth,
                asset.depth,
                excavation.radius_meters,
            )
            spatial.append(
                SpatialConflict(
                    kind="infrastructure",
                    target_id=asset.asset_id,
                    target_name=f"{asset.type} ({asset.asset_id})",
                    distance_meters=round(d, 2),
                    severity=_infra_severity_from_index(idx),
                )
            )

    for proj in projects:
        if proj.project_id == excavation.request_id:
            continue
        d = haversine_m(
            excavation.latitude,
            excavation.longitude,
            proj.latitude,
            proj.longitude,
        )
        if d <= excavation.radius_meters + proj.radius_meters:
            spatial.append(
                SpatialConflict(
                    kind="project_site",
                    target_id=proj.project_id,
                    target_name=proj.name,
                    distance_meters=round(d, 2),
                    severity=_project_spatial_severity(d, proj.status),
                )
            )
        overlap = _overlap_days(
            excavation.start_date, excavation.end_date, proj.start_date, proj.end_date
        )
        if overlap > 0 and d <= excavation.radius_meters + proj.radius_meters + 45.0:
            temporal.append(
                TemporalConflict(
                    kind="schedule_overlap",
                    project_id=proj.project_id,
                    project_name=proj.name,
                    overlap_days=overlap,
                    severity=_temporal_severity(overlap, excavation),
                )
            )

    return DetectedConflicts(spatial=spatial, temporal=temporal)


def incident_proximity_count(excavation: ExcavationRequest, incidents: list[HistoricalIncident]) -> int:
    n = 0
    for inc in incidents:
        if (
            haversine_m(excavation.latitude, excavation.longitude, inc.latitude, inc.longitude)
            <= INCIDENT_RADIUS_M
        ):
            n += 1
    return n


def incident_weighted_stress(excavation: ExcavationRequest, incidents: list[HistoricalIncident]) -> float:
    """0+ aggregate severity weight inside INCIDENT_RADIUS_M for risk scoring."""
    sev_w = {"Low": 0.35, "Medium": 0.75, "High": 1.15, "Critical": 1.45}
    total = 0.0
    for inc in incidents:
        d = haversine_m(excavation.latitude, excavation.longitude, inc.latitude, inc.longitude)
        if d > INCIDENT_RADIUS_M:
            continue
        w = sev_w.get(inc.severity, 0.75)
        total += w * max(0.0, 1.0 - d / INCIDENT_RADIUS_M)
    return total


def nearby_project_density(excavation: ExcavationRequest, projects: list[Project], radius_m: float = 80.0) -> int:
    count = 0
    for p in projects:
        if haversine_m(excavation.latitude, excavation.longitude, p.latitude, p.longitude) > radius_m:
            continue
        if _overlap_days(excavation.start_date, excavation.end_date, p.start_date, p.end_date) == 0:
            continue
        count += 1
    return count


def count_infrastructure_within(excavation: ExcavationRequest, infrastructure: list[InfrastructureAsset], radius_m: float) -> int:
    n = 0
    for a in infrastructure:
        if haversine_m(excavation.latitude, excavation.longitude, a.latitude, a.longitude) <= radius_m:
            n += 1
    return n
