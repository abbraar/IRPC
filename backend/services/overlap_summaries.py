"""Typed overlap summaries for manual location analysis (map/UI enrichment)."""

from __future__ import annotations

from datetime import date
from typing import Any

from models import (
    HistoricalIncident,
    InfrastructureAsset,
    InfrastructureOverlapDetail,
    LocationAnalysisInput,
    Project,
    ProjectOverlapDetail,
    TemporalOverlapDetail,
)
from services.conflict_detection import haversine_m

# Re-export for tests; incident radius matches conflict_detection.INCIDENT_RADIUS_M
INCIDENT_RADIUS_M = 150.0


def _overlap_days(a_start: date, a_end: date, b_start: date, b_end: date) -> int:
    start = max(a_start, b_start)
    end = min(a_end, b_end)
    if start > end:
        return 0
    return (end - start).days + 1


def _severity_from_asset(asset: InfrastructureAsset, distance_m: float, payload: LocationAnalysisInput) -> str:
    depth_conflict = payload.depth >= asset.depth - 0.35
    very_close = distance_m <= max(5.0, payload.work_radius * 0.45)
    if asset.criticality == "High" and depth_conflict and very_close:
        return "High"
    if asset.criticality == "High" or depth_conflict or distance_m <= payload.work_radius:
        return "Medium"
    return "Low"


def _severity_from_project(spatial: bool, temporal_days: int) -> str:
    if spatial and temporal_days >= 14:
        return "High"
    if spatial and temporal_days > 0:
        return "Medium"
    if spatial:
        return "Medium"
    if temporal_days > 0:
        return "Low"
    return "Low"


def collect_overlap_summaries(
    payload: LocationAnalysisInput,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> tuple[
    list[InfrastructureOverlapDetail],
    list[ProjectOverlapDetail],
    list[TemporalOverlapDetail],
    list[InfrastructureAsset],
    list[Project],
    list[HistoricalIncident],
]:
    """
    Build typed overlap rows and map context layers around the submitted coordinate.
    Scoring uses detect_conflicts/compute_risk separately; this enriches the API response.
    """
    lat, lon = payload.latitude, payload.longitude
    infrastructure_overlaps: list[InfrastructureOverlapDetail] = []
    context_asset_ids: set[str] = set()

    for asset in infrastructure:
        distance = haversine_m(lat, lon, asset.latitude, asset.longitude)
        threshold = payload.work_radius + asset.influence_radius
        if distance <= threshold + 95:
            context_asset_ids.add(asset.asset_id)
        if distance <= threshold:
            depth_conflict = payload.depth >= asset.depth - 0.35
            severity = _severity_from_asset(asset, distance, payload)
            infrastructure_overlaps.append(
                InfrastructureOverlapDetail(
                    asset_id=asset.asset_id,
                    type=asset.type,
                    latitude=asset.latitude,
                    longitude=asset.longitude,
                    distance_meters=round(distance, 2),
                    asset_depth=asset.depth,
                    criticality=asset.criticality,
                    influence_radius=asset.influence_radius,
                    sensitivity_score=asset.sensitivity_score,
                    depth_conflict=depth_conflict,
                    severity=severity,  # type: ignore[arg-type]
                )
            )

    project_overlaps: list[ProjectOverlapDetail] = []
    temporal_overlaps: list[TemporalOverlapDetail] = []
    context_project_ids: set[str] = set()

    for project in projects:
        distance = haversine_m(lat, lon, project.latitude, project.longitude)
        spatial = distance <= payload.work_radius + project.radius_meters
        temporal_days = _overlap_days(payload.start_date, payload.end_date, project.start_date, project.end_date)
        severity = _severity_from_project(spatial, temporal_days)
        if distance <= payload.work_radius + project.radius_meters + 125:
            context_project_ids.add(project.project_id)
        if spatial:
            project_overlaps.append(
                ProjectOverlapDetail(
                    project_id=project.project_id,
                    name=project.name,
                    latitude=project.latitude,
                    longitude=project.longitude,
                    distance_meters=round(distance, 2),
                    radius_meters=project.radius_meters,
                    status=project.status,
                    severity=severity,  # type: ignore[arg-type]
                    has_temporal_overlap=temporal_days > 0,
                    overlap_days=temporal_days,
                )
            )
        if temporal_days > 0 and distance <= payload.work_radius + project.radius_meters + 45:
            temporal_overlaps.append(
                TemporalOverlapDetail(
                    project_id=project.project_id,
                    name=project.name,
                    start_date=project.start_date.isoformat(),
                    end_date=project.end_date.isoformat(),
                    overlap_days=temporal_days,
                    spatial_overlap=spatial,
                    severity=severity,  # type: ignore[arg-type]
                )
            )

    context_incident_ids: set[str] = set()
    for incident in incidents:
        if haversine_m(lat, lon, incident.latitude, incident.longitude) <= INCIDENT_RADIUS_M:
            context_incident_ids.add(incident.incident_id)

    context_infrastructure = [a for a in infrastructure if a.asset_id in context_asset_ids][:16]
    context_projects = [p for p in projects if p.project_id in context_project_ids][:10]
    context_incidents = [i for i in incidents if i.incident_id in context_incident_ids][:8]

    return (
        infrastructure_overlaps,
        project_overlaps,
        temporal_overlaps,
        context_infrastructure,
        context_projects,
        context_incidents,
    )


def legacy_conflicts_list(
    infrastructure_overlaps: list[InfrastructureOverlapDetail],
    project_overlaps: list[ProjectOverlapDetail],
    temporal_overlaps: list[TemporalOverlapDetail],
) -> list[dict[str, Any]]:
    """Flatten typed overlaps into the legacy `conflicts` array shape for existing clients."""
    return [
        *[{"kind": "infrastructure", **item.model_dump(mode="json")} for item in infrastructure_overlaps],
        *[{"kind": "project", **item.model_dump(mode="json")} for item in project_overlaps],
        *[{"kind": "temporal", **item.model_dump(mode="json")} for item in temporal_overlaps],
    ]
