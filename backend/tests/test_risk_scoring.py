from datetime import date

from models import ExcavationRequest
from services.conflict_detection import detect_conflicts
from services.risk_scoring import compute_risk


def _excavation(**kwargs) -> ExcavationRequest:
    base = dict(
        request_id="T-1",
        latitude=24.828315,
        longitude=46.676244,
        depth=2.0,
        radius_meters=10.0,
        start_date=date(2026, 5, 12),
        end_date=date(2026, 6, 19),
        excavation_type="Open Cut",
        contractor_name="Test",
    )
    base.update(kwargs)
    return ExcavationRequest(**base)


def test_compute_risk_returns_bounded_score_and_level():
    exc = _excavation()
    conflicts = detect_conflicts(exc, [], [])
    risk = compute_risk(exc, conflicts, [], [], [])

    assert 0 <= risk.risk_score <= 100
    assert risk.risk_level in {"Low", "Medium", "High"}
    assert risk.contributing_factors
    assert 0.42 <= risk.confidence_score <= 0.92


def test_deeper_excavation_increases_geometry_contribution():
    shallow = _excavation(depth=0.5)
    deep = _excavation(depth=5.0)
    c_shallow = detect_conflicts(shallow, [], [])
    c_deep = detect_conflicts(deep, [], [])
    r_shallow = compute_risk(shallow, c_shallow, [], [], [])
    r_deep = compute_risk(deep, c_deep, [], [], [])

    shallow_pts = next(f.weight_contribution for f in r_shallow.contributing_factors if f.factor == "geometry_depth")
    deep_pts = next(f.weight_contribution for f in r_deep.contributing_factors if f.factor == "geometry_depth")
    assert deep_pts >= shallow_pts
