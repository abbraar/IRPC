from datetime import date
from unittest.mock import patch

from models import DetectedConflicts, ExcavationRequest, RiskResult, ContributingFactor
from services.narrative_provider import RuleBasedNarrativeProvider, generate_narrative


def _minimal_risk() -> RiskResult:
    factor = ContributingFactor(
        factor="geometry_depth",
        display_name="Depth",
        category="Geometry",
        weight_contribution=5.0,
        pct_of_composite=100.0,
        detail="test",
    )
    return RiskResult(
        risk_score=25.0,
        risk_level="Low",
        contributing_factors=[factor],
        confidence_score=0.75,
        confidence_rationale="test rationale",
    )


def test_generate_narrative_uses_fallback_when_gemini_disabled():
    exc = ExcavationRequest(
        request_id="T-4",
        latitude=24.828315,
        longitude=46.676244,
        depth=2.0,
        radius_meters=10.0,
        start_date=date(2026, 5, 12),
        end_date=date(2026, 6, 19),
        excavation_type="Open Cut",
        contractor_name="Test",
    )
    conflicts = DetectedConflicts(spatial=[], temporal=[])
    risk = _minimal_risk()
    fallback = RuleBasedNarrativeProvider()

    with patch("services.narrative_provider.ai_narrative_enabled", return_value=False):
        explanation, recommendations, source = generate_narrative(
            exc, conflicts, risk, use_ai=True, fallback=fallback
        )

    assert source == "deterministic"
    assert "ASSESSMENT SUMMARY" in explanation
    assert recommendations


def test_generate_narrative_falls_back_on_gemini_error():
    exc = ExcavationRequest(
        request_id="T-5",
        latitude=24.828315,
        longitude=46.676244,
        depth=2.0,
        radius_meters=10.0,
        start_date=date(2026, 5, 12),
        end_date=date(2026, 6, 19),
        excavation_type="Open Cut",
        contractor_name="Test",
    )
    conflicts = DetectedConflicts(spatial=[], temporal=[])
    risk = _minimal_risk()
    fallback = RuleBasedNarrativeProvider()

    with patch("services.narrative_provider.ai_narrative_enabled", return_value=True):
        with patch(
            "services.narrative_provider.GeminiNarrativeProvider.generate_explanation",
            side_effect=RuntimeError("api down"),
        ):
            explanation, recommendations, source = generate_narrative(
                exc, conflicts, risk, use_ai=True, fallback=fallback
            )

    assert source == "deterministic"
    assert recommendations
