from datetime import date

from models import LocationAnalysisInput
from services.location_analysis import analyze_manual_location


def payload(
    *,
    depth: float,
    work_radius: float,
    start_date: date = date(2026, 5, 12),
    end_date: date = date(2026, 6, 19),
    language: str = "en",
) -> LocationAnalysisInput:
    return LocationAnalysisInput(
        longitude=46.676244,
        latitude=24.828315,
        depth=depth,
        work_radius=work_radius,
        start_date=start_date,
        end_date=end_date,
        language=language,
    )


def analyze(request: LocationAnalysisInput):
    return analyze_manual_location(request, infrastructure=[], projects=[], incidents=[])


def test_low_risk_scenario_has_low_level():
    result = analyze(
        payload(
            depth=0.5,
            work_radius=1.0,
            start_date=date(2026, 5, 12),
            end_date=date(2026, 5, 13),
        )
    )

    assert result.risk_level == "Low"
    assert result.risk_score <= 30


def test_medium_risk_scenario_has_medium_level():
    result = analyze(payload(depth=2.0, work_radius=10.0))

    assert result.risk_level == "Medium"
    assert 30 < result.risk_score <= 70
    assert result.infrastructure_overlaps


def test_high_risk_scenario_has_high_level():
    result = analyze(payload(depth=5.0, work_radius=40.0))

    assert result.risk_level == "High"
    assert result.risk_score > 70
    assert any(item["type"] == "Gas Pipeline" and item["severity"] == "High" for item in result.infrastructure_overlaps)
    assert result.temporal_overlaps


def test_larger_radius_produces_higher_or_equal_risk():
    small = analyze(payload(depth=2.5, work_radius=5.0))
    large = analyze(payload(depth=2.5, work_radius=35.0))

    assert large.risk_score >= small.risk_score


def test_deeper_excavation_produces_higher_or_equal_risk():
    shallow = analyze(payload(depth=0.8, work_radius=12.0))
    deep = analyze(payload(depth=5.0, work_radius=12.0))

    assert deep.risk_score >= shallow.risk_score


def test_temporal_overlap_is_detected_for_overlapping_schedule():
    result = analyze(payload(depth=2.0, work_radius=12.0))

    assert result.temporal_overlaps
    assert any(item["overlap_days"] > 0 for item in result.temporal_overlaps)


def test_arabic_output_returns_arabic_text():
    result = analyze(payload(depth=5.0, work_radius=40.0, language="ar"))

    assert result.risk_level_label == "عالي الخطورة"
    assert "ملخص التقييم" in result.explanation
    assert result.recommendations
    assert any("مراجعة هندسية" in item.action for item in result.recommendations)


def test_neighborhood_context_flags_outside_demo_area():
    request = payload(depth=2.0, work_radius=10.0)
    request.longitude = 46.90
    request.latitude = 24.90

    result = analyze(request)

    assert result.neighborhood_context["is_inside_demo_area"] is False
    assert result.neighborhood_context["boundary"]
