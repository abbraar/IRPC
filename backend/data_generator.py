"""
Synthetic data generator for stakeholder demos.

Places a share of infrastructure, projects, and incidents **near** excavations with
overlapping schedules so conflicts and risk scores are demonstrably linked — not
purely independent draws (easy to swap for API-backed geometry later).
"""

from __future__ import annotations

import json
import math
import random
import uuid
from datetime import date, timedelta
from pathlib import Path

from models import (
    ExcavationRequest,
    FakeDataStore,
    HistoricalIncident,
    InfrastructureAsset,
    Project,
)

# Demo bbox around An Narjis District, Riyadh.
REGION_CENTER_LAT = 24.828315
REGION_CENTER_LON = 46.676244
EXAMPLE_LAT = 24.828315
EXAMPLE_LON = 46.676244
LAT_SPREAD = 0.006
LON_SPREAD = 0.008

ASSET_TYPES = [
    "Gas Pipeline",
    "Water Pipe",
    "Electrical Cable",
    "Telecom Line",
]

EXC_TYPES = ["Open Cut", "Trenchless", "Potholing", "Directional Drill", "Sheet Pile"]
CONTRACTORS = ["Nordic Civil", "Delta Infra", "UrbanLink", "GeoSafe BV", "HarborWorks"]
PROJECT_NAMES = ["Fiber Ring East", "District Heating Phase 2", "Tram Power Upgrade", "Storm Drain Rehab"]
INCIDENT_TYPES = ["Third-party strike", "Shallow miss-locate", "Unknown utility", "Overpressure", "Flooding"]


def _rand_point(rng: random.Random) -> tuple[float, float]:
    lat = REGION_CENTER_LAT + (rng.random() - 0.5) * LAT_SPREAD
    lon = REGION_CENTER_LON + (rng.random() - 0.5) * LON_SPREAD
    return lat, lon


def _offset_meters(lat: float, lon: float, dist_m: float, bearing_deg: float) -> tuple[float, float]:
    """Small flat-earth offset for short synthetic ties (not survey-grade)."""
    br = math.radians(bearing_deg)
    dlat = (dist_m * math.cos(br)) / 111_320.0
    dlon = (dist_m * math.sin(br)) / (111_320.0 * max(0.2, math.cos(math.radians(lat))))
    return lat + dlat, lon + dlon


def _rand_date_span(rng: random.Random, base: date) -> tuple[date, date]:
    start = base + timedelta(days=rng.randint(-20, 40))
    end = start + timedelta(days=rng.randint(5, 45))
    return start, end


def _choose_high_risk_indices(rng: random.Random, n_excavations: int) -> set[int]:
    """Randomly choose 2-4 requests to become high-risk demo scenarios."""
    if n_excavations <= 0:
        return set()
    max_high = min(4, n_excavations)
    min_high = min(2, max_high)
    high_count = rng.randint(min_high, max_high)
    return set(rng.sample(range(n_excavations), high_count))


def generate_fake_data(
    seed: int = 42,
    n_excavations: int = 8,
    n_assets: int = 24,
    n_projects: int = 10,
    n_incidents: int = 14,
) -> FakeDataStore:
    rng = random.Random(seed)
    base = date.today()
    high_risk_indices = _choose_high_risk_indices(rng, n_excavations)

    excavations: list[ExcavationRequest] = []
    for i in range(n_excavations):
        lat, lon = _rand_point(rng)
        start, end = _rand_date_span(rng, base)
        is_high = i in high_risk_indices
        if is_high:
            start = base + timedelta(days=rng.randint(-4, 18))
            end = start + timedelta(days=rng.randint(24, 46))
        excavations.append(
            ExcavationRequest(
                request_id=f"EXC-{1000 + i}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                depth=round(rng.uniform(4.0, 5.0) if is_high else rng.uniform(0.8, 4.5), 2),
                radius_meters=round(rng.uniform(15.0, 20.0) if is_high else rng.uniform(3, 14), 1),
                start_date=start,
                end_date=end,
                excavation_type=rng.choice(["Open Cut", "Sheet Pile"]) if is_high else rng.choice(EXC_TYPES),
                contractor_name=rng.choice(CONTRACTORS),
            )
        )

    infrastructure: list[InfrastructureAsset] = []
    asset_idx = 0

    # Manual-entry demo cluster around An Narjis District, Riyadh.
    example_assets = [
        ("Gas Pipeline", 5.0, 35, 1.65, "High", 14.0, 98.0),
        ("Water Pipe", 16.0, 120, 2.1, "Medium", 10.0, 72.0),
        ("Electrical Cable", 9.5, 240, 1.35, "High", 12.0, 93.0),
        ("Telecom Line", 24.0, 310, 1.0, "Low", 7.0, 44.0),
    ]
    for type_name, dist, bearing, depth, criticality, influence_radius, sensitivity in example_assets:
        if len(infrastructure) >= n_assets:
            break
        lat, lon = _offset_meters(EXAMPLE_LAT, EXAMPLE_LON, dist, bearing)
        infrastructure.append(
            InfrastructureAsset(
                asset_id=f"AST-{2000 + asset_idx}",
                type=type_name,  # type: ignore[arg-type]
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                depth=depth,
                criticality=criticality,  # type: ignore[arg-type]
                influence_radius=influence_radius,
                sensitivity_score=sensitivity,
            )
        )
        asset_idx += 1

    # High-risk demo clusters: multiple critical utilities very close to a
    # random subset of excavations, with depths inside the excavation envelope.
    for high_idx in sorted(high_risk_indices):
        if len(infrastructure) >= n_assets:
            break
        exc = excavations[high_idx]
        high_asset_templates = [
            ("Gas Pipeline", rng.uniform(2.0, 4.5), rng.uniform(0, 360), rng.uniform(1.2, 2.0), rng.uniform(94, 99)),
            ("Electrical Cable", rng.uniform(3.0, 6.5), rng.uniform(0, 360), rng.uniform(1.0, 1.8), rng.uniform(90, 97)),
            ("Gas Pipeline", rng.uniform(5.0, 9.0), rng.uniform(0, 360), rng.uniform(1.8, 2.8), rng.uniform(88, 96)),
            ("Water Pipe", rng.uniform(7.0, 12.0), rng.uniform(0, 360), rng.uniform(1.4, 2.6), rng.uniform(80, 90)),
        ]
        assets_for_cluster = rng.randint(3, 4)
        for type_name, dist, bearing, depth, sensitivity in high_asset_templates[:assets_for_cluster]:
            if len(infrastructure) >= n_assets:
                break
            lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, bearing)
            infrastructure.append(
                InfrastructureAsset(
                    asset_id=f"AST-{2000 + asset_idx}",
                    type=type_name,  # type: ignore[arg-type]
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    depth=round(depth, 2),
                    criticality="High",
                    influence_radius=round(rng.uniform(10.0, 16.0), 1),
                    sensitivity_score=round(sensitivity, 1),
                )
            )
            asset_idx += 1

    # Correlated assets: bury utilities plausible distances from several excavations
    for idx, exc in enumerate(excavations[: min(6, len(excavations))]):
        if idx in high_risk_indices:
            continue
        if len(infrastructure) >= n_assets:
            break
        n_near = rng.randint(1, 2) if len(infrastructure) + 2 <= n_assets else 1
        for _ in range(n_near):
            if len(infrastructure) >= n_assets:
                break
            dist = rng.uniform(4.0, 22.0)
            bearing = rng.uniform(0, 360)
            lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, bearing)
            type_name = rng.choice(ASSET_TYPES)
            criticality = rng.choices(["Low", "Medium", "High"], weights=[0.2, 0.4, 0.4])[0]
            if type_name == "Gas Pipeline":
                criticality = rng.choices(["Medium", "High"], weights=[0.3, 0.7])[0]
            # Asset depth often near or above trench bottom (simplified strike scenario)
            asset_depth = round(max(0.9, min(exc.depth + rng.uniform(-0.8, 1.2), 4.0)), 2)
            infrastructure.append(
                InfrastructureAsset(
                    asset_id=f"AST-{2000 + asset_idx}",
                    type=type_name,  # type: ignore[arg-type]
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    depth=asset_depth,
                    criticality=criticality,  # type: ignore[arg-type]
                    influence_radius=round(rng.uniform(6.0, 12.0), 1),
                    sensitivity_score=round(
                        rng.uniform(55, 96) if criticality == "High" else rng.uniform(25, 80), 1
                    ),
                )
            )
            asset_idx += 1

    # Fill remaining slots with background corridor assets
    while len(infrastructure) < n_assets:
        lat, lon = _rand_point(rng)
        type_name = rng.choice(ASSET_TYPES)
        criticality = rng.choices(["Low", "Medium", "High"], weights=[0.25, 0.45, 0.3])[0]
        if type_name == "Gas Pipeline":
            criticality = rng.choices(["Medium", "High"], weights=[0.35, 0.65])[0]
        infrastructure.append(
            InfrastructureAsset(
                asset_id=f"AST-{2000 + asset_idx}",
                type=type_name,  # type: ignore[arg-type]
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                depth=round(rng.uniform(1.0, 3.5), 2),
                criticality=criticality,  # type: ignore[arg-type]
                influence_radius=round(rng.uniform(5.0, 11.0), 1),
                sensitivity_score=round(
                    rng.uniform(40, 95) if criticality == "High" else rng.uniform(20, 75), 1
                ),
            )
        )
        asset_idx += 1

    projects: list[Project] = []
    proj_idx = 0

    example_projects = [
        ("Ongoing Road Renewal", 18.0, 65, 28.0, date(2026, 5, 20), date(2026, 6, 10), "Active"),
        ("Water Network Maintenance", 34.0, 210, 22.0, date(2026, 5, 8), date(2026, 5, 28), "Active"),
        ("Telecom Duct Survey", 62.0, 300, 18.0, date(2026, 6, 5), date(2026, 6, 22), "Planning"),
    ]
    for name, dist, bearing, radius, start, end, status in example_projects:
        if len(projects) >= n_projects:
            break
        lat, lon = _offset_meters(EXAMPLE_LAT, EXAMPLE_LON, dist, bearing)
        projects.append(
            Project(
                project_id=f"PRJ-{3000 + proj_idx}",
                name=f"{name} #{proj_idx + 1}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                radius_meters=radius,
                start_date=start,
                end_date=end,
                status=status,
            )
        )
        proj_idx += 1

    # High-risk demo clusters: active nearby projects that overlap the selected
    # high-risk excavations, driving temporal and coordination pressure.
    for high_idx in sorted(high_risk_indices):
        if len(projects) >= n_projects:
            break
        exc = excavations[high_idx]
        high_project_templates = [
            ("Emergency Gas Valve Replacement", rng.uniform(7.0, 14.0), rng.uniform(0, 360), rng.randint(-3, 3), rng.randint(20, 34)),
            ("Feeder Cable Diversion", rng.uniform(10.0, 20.0), rng.uniform(0, 360), rng.randint(-2, 5), rng.randint(22, 38)),
            ("Storm Main Tie-in", rng.uniform(18.0, 30.0), rng.uniform(0, 360), rng.randint(0, 8), rng.randint(16, 32)),
        ]
        projects_for_cluster = rng.randint(2, 3)
        for name, dist, bearing, start_offset, duration in high_project_templates[:projects_for_cluster]:
            if len(projects) >= n_projects:
                break
            lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, bearing)
            p_start = exc.start_date + timedelta(days=start_offset)
            projects.append(
                Project(
                    project_id=f"PRJ-{3000 + proj_idx}",
                    name=f"{name} #{proj_idx + 1}",
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    radius_meters=round(rng.uniform(18.0, 32.0), 1),
                    start_date=p_start,
                    end_date=p_start + timedelta(days=duration),
                    status="Active",
                )
            )
            proj_idx += 1

    # Half of projects tied to excavation sites + overlapping schedules (coordination story)
    tied = min(max(0, n_projects - len(projects)), n_projects // 2 + 1, len(excavations))
    used_exc: set[int] = set()
    for _ in range(tied):
        unused = [i for i in range(len(excavations)) if i not in used_exc]
        if not unused:
            break
        idx = rng.choice(unused)
        used_exc.add(idx)
        exc = excavations[idx]
        dist = rng.uniform(12.0, 55.0)
        lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, rng.uniform(0, 360))
        # Guaranteed schedule overlap with the paired excavation (coordination / congestion demo)
        p_start = exc.start_date + timedelta(days=rng.randint(-3, 6))
        p_end = exc.end_date + timedelta(days=rng.randint(0, 18))
        if p_end <= p_start:
            p_end = p_start + timedelta(days=21)
        projects.append(
            Project(
                project_id=f"PRJ-{3000 + proj_idx}",
                name=f"{rng.choice(PROJECT_NAMES)} #{proj_idx + 1}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                radius_meters=round(rng.uniform(14.0, 28.0), 1),
                start_date=p_start,
                end_date=p_end,
                status=rng.choice(["Planning", "Active", "Active", "On hold"]),
            )
        )
        proj_idx += 1

    while len(projects) < n_projects:
        lat, lon = _rand_point(rng)
        start, end = _rand_date_span(rng, base)
        projects.append(
            Project(
                project_id=f"PRJ-{3000 + proj_idx}",
                name=f"{rng.choice(PROJECT_NAMES)} #{proj_idx + 1}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                radius_meters=round(rng.uniform(12.0, 26.0), 1),
                start_date=start,
                end_date=end,
                status=rng.choice(["Planning", "Active", "Active", "On hold"]),
            )
        )
        proj_idx += 1

    incidents: list[HistoricalIncident] = []
    example_incidents = [
        ("Third-party strike", "Critical", "Gas Pipeline", 22.0, 150),
        ("Unknown utility", "High", "Electrical Cable", 48.0, 260),
        ("Flooding", "Medium", "Water Pipe", 72.0, 20),
    ]
    for incident_type, severity, asset_type, dist, bearing in example_incidents:
        if len(incidents) >= n_incidents:
            break
        lat, lon = _offset_meters(EXAMPLE_LAT, EXAMPLE_LON, dist, bearing)
        incidents.append(
            HistoricalIncident(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                incident_type=incident_type,
                severity=severity,  # type: ignore[arg-type]
                related_asset_type=asset_type,
            )
        )

    # High-risk demo clusters: nearby severe incidents reinforce corridor history.
    for high_idx in sorted(high_risk_indices):
        if len(incidents) >= n_incidents:
            break
        exc = excavations[high_idx]
        high_incident_templates = [
            ("Third-party strike", "Critical", "Gas Pipeline", rng.uniform(14, 28), rng.uniform(0, 360)),
            ("Unknown utility", "High", "Electrical Cable", rng.uniform(25, 52), rng.uniform(0, 360)),
            ("Shallow miss-locate", "High", "Gas Pipeline", rng.uniform(35, 70), rng.uniform(0, 360)),
        ]
        incidents_for_cluster = rng.randint(2, 3)
        for incident_type, severity, asset_type, dist, bearing in high_incident_templates[:incidents_for_cluster]:
            if len(incidents) >= n_incidents:
                break
            lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, bearing)
            incidents.append(
                HistoricalIncident(
                    incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                    latitude=round(lat, 6),
                    longitude=round(lon, 6),
                    incident_type=incident_type,
                    severity=severity,  # type: ignore[arg-type]
                    related_asset_type=asset_type,
                )
            )

    # Incidents clustered near excavation corridors (repeat strike risk narrative)
    clustered = max(0, min(n_incidents - len(incidents), 10))
    for _ in range(clustered):
        exc = rng.choice(excavations)
        dist = rng.uniform(15.0, 130.0)
        lat, lon = _offset_meters(exc.latitude, exc.longitude, dist, rng.uniform(0, 360))
        incidents.append(
            HistoricalIncident(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                incident_type=rng.choice(INCIDENT_TYPES),
                severity=rng.choices(["Low", "Medium", "High", "Critical"], weights=[0.15, 0.35, 0.4, 0.1])[0],  # type: ignore[arg-type]
                related_asset_type=rng.choice(["Gas Pipeline", "Water Pipe", "Electrical Cable", "Telecom Line"]),
            )
        )
    while len(incidents) < n_incidents:
        lat, lon = _rand_point(rng)
        incidents.append(
            HistoricalIncident(
                incident_id=f"INC-{uuid.uuid4().hex[:8].upper()}",
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                incident_type=rng.choice(INCIDENT_TYPES),
                severity=rng.choices(["Low", "Medium", "High", "Critical"], weights=[0.2, 0.35, 0.35, 0.1])[0],  # type: ignore[arg-type]
                related_asset_type=rng.choice(["Gas Pipeline", "Water Pipe", "Electrical Cable", "Telecom Line"]),
            )
        )

    return FakeDataStore(
        excavations=excavations,
        infrastructure=infrastructure,
        projects=projects,
        incidents=incidents,
    )


def save_store(path: Path, store: FakeDataStore) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store.model_dump(mode="json"), indent=2), encoding="utf-8")


def load_store(path: Path) -> FakeDataStore | None:
    if not path.exists():
        return None
    return FakeDataStore.model_validate_json(path.read_text(encoding="utf-8"))
