"""Generate local synthetic infrastructure/projects/incidents around a manual coordinate."""

from __future__ import annotations

import math
from datetime import timedelta

from config.demo_neighborhood import (
    NEIGHBORHOOD_CENTER,
    clamp_to_demo_bounds,
    is_point_inside_demo_area,
)
from models import (
    HistoricalIncident,
    InfrastructureAsset,
    LocationAnalysisInput,
    Project,
)


def _offset_meters(lat: float, lon: float, dist_m: float, bearing_deg: float) -> tuple[float, float]:
    bearing = math.radians(bearing_deg)
    dlat = (dist_m * math.cos(bearing)) / 111_320.0
    dlon = (dist_m * math.sin(bearing)) / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def generate_local_synthetic_context(
    payload: LocationAnalysisInput,
) -> tuple[list[InfrastructureAsset], list[Project], list[HistoricalIncident]]:
    """Deterministic local context around submitted coordinates for demo continuity."""
    submitted_lat, submitted_lon = payload.latitude, payload.longitude
    if is_point_inside_demo_area(submitted_lat, submitted_lon):
        lat, lon = submitted_lat, submitted_lon
    else:
        lat, lon = NEIGHBORHOOD_CENTER

    asset_templates = [
        ("CTX-AST-GAS", "Gas Pipeline", 8.0, 35.0, 1.65, "High", 14.0, 96.0),
        ("CTX-AST-WATER", "Water Pipe", 18.0, 118.0, 2.1, "Medium", 10.0, 72.0),
        ("CTX-AST-ELEC", "Electrical Cable", 34.0, 240.0, 1.35, "High", 9.0, 91.0),
        ("CTX-AST-TEL", "Telecom Line", 58.0, 315.0, 1.0, "Low", 7.0, 45.0),
    ]
    context_assets: list[InfrastructureAsset] = []
    for asset_id, type_name, dist, bearing, depth, criticality, influence, sensitivity in asset_templates:
        asset_lat, asset_lon = _offset_meters(lat, lon, dist, bearing)
        asset_lat, asset_lon = clamp_to_demo_bounds(asset_lat, asset_lon)
        context_assets.append(
            InfrastructureAsset(
                asset_id=asset_id,
                type=type_name,  # type: ignore[arg-type]
                latitude=round(asset_lat, 6),
                longitude=round(asset_lon, 6),
                depth=depth,
                criticality=criticality,  # type: ignore[arg-type]
                influence_radius=influence,
                sensitivity_score=sensitivity,
            )
        )

    project_templates = [
        ("CTX-PRJ-ROAD", "Ongoing Road Project", 22.0, 70.0, 26.0, -2, 24, "Active"),
        ("CTX-PRJ-MAINT", "Water Network Maintenance", 48.0, 210.0, 22.0, 8, 30, "Active"),
        ("CTX-PRJ-TELECOM", "Telecom Duct Survey", 86.0, 305.0, 20.0, 18, 38, "Planning"),
    ]
    context_projects: list[Project] = []
    for project_id, name, dist, bearing, radius, start_offset, duration, status in project_templates:
        project_lat, project_lon = _offset_meters(lat, lon, dist, bearing)
        project_lat, project_lon = clamp_to_demo_bounds(project_lat, project_lon)
        start = payload.start_date + timedelta(days=start_offset)
        context_projects.append(
            Project(
                project_id=project_id,
                name=name,
                latitude=round(project_lat, 6),
                longitude=round(project_lon, 6),
                radius_meters=radius,
                start_date=start,
                end_date=start + timedelta(days=duration),
                status=status,
            )
        )

    incident_templates = [
        ("CTX-INC-GAS", "Third-party strike", "High", "Gas Pipeline", 38.0, 150.0),
        ("CTX-INC-UNKNOWN", "Unknown utility", "Medium", "Electrical Cable", 92.0, 260.0),
    ]
    context_incidents: list[HistoricalIncident] = []
    for incident_id, incident_type, severity, asset_type, dist, bearing in incident_templates:
        inc_lat, inc_lon = _offset_meters(lat, lon, dist, bearing)
        inc_lat, inc_lon = clamp_to_demo_bounds(inc_lat, inc_lon)
        context_incidents.append(
            HistoricalIncident(
                incident_id=incident_id,
                latitude=round(inc_lat, 6),
                longitude=round(inc_lon, 6),
                incident_type=incident_type,
                severity=severity,  # type: ignore[arg-type]
                related_asset_type=asset_type,
            )
        )
    return context_assets, context_projects, context_incidents
