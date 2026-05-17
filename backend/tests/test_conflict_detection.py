from datetime import date

from models import ExcavationRequest, InfrastructureAsset, Project
from services.conflict_detection import detect_conflicts, haversine_m


def test_haversine_zero_distance():
    assert haversine_m(24.828315, 46.676244, 24.828315, 46.676244) == 0.0


def test_infrastructure_spatial_conflict_detected():
    exc = ExcavationRequest(
        request_id="T-2",
        latitude=24.828315,
        longitude=46.676244,
        depth=3.0,
        radius_meters=15.0,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 5, 30),
        excavation_type="Open Cut",
        contractor_name="Test",
    )
    asset = InfrastructureAsset(
        asset_id="A-1",
        type="Gas Pipeline",
        latitude=24.82832,
        longitude=46.67625,
        depth=1.5,
        criticality="High",
        influence_radius=10.0,
        sensitivity_score=90.0,
    )
    conflicts = detect_conflicts(exc, [asset], [])
    infra = [c for c in conflicts.spatial if c.kind == "infrastructure"]
    assert infra
    assert infra[0].severity in {"Low", "Medium", "High"}


def test_temporal_conflict_when_schedules_overlap():
    exc = ExcavationRequest(
        request_id="T-3",
        latitude=24.828315,
        longitude=46.676244,
        depth=2.0,
        radius_meters=20.0,
        start_date=date(2026, 5, 10),
        end_date=date(2026, 5, 20),
        excavation_type="Open Cut",
        contractor_name="Test",
    )
    project = Project(
        project_id="P-1",
        name="Nearby work",
        latitude=24.82832,
        longitude=46.67625,
        radius_meters=25.0,
        start_date=date(2026, 5, 1),
        end_date=date(2026, 6, 1),
        status="Active",
    )
    conflicts = detect_conflicts(exc, [], [project])
    assert conflicts.temporal
    assert conflicts.temporal[0].overlap_days > 0
