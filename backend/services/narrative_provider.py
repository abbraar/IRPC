"""
Pluggable narrative providers for analyst explanation and recommendations.

Swap Gemini for OpenAI-compatible providers later by implementing NarrativeProvider.
"""

from __future__ import annotations

import logging
import os
from typing import Literal, Protocol

from models import (
    DetectedConflicts,
    ExcavationRequest,
    InfrastructureOverlapDetail,
    LocationAnalysisInput,
    ProjectOverlapDetail,
    RecommendationItem,
    RiskResult,
    TemporalOverlapDetail,
)
from services.explainability import build_explanation
from services.gemini_service import (
    GeminiServiceError,
    generate_explanation as gemini_generate_explanation,
    generate_recommendations as gemini_generate_recommendations,
    narrative_layer_status,
)
from services.location_narrative import build_location_explanation, build_location_recommendations
from services.recommendation import recommend

logger = logging.getLogger(__name__)

NarrativeSource = Literal["gemini", "deterministic", "location_template"]


class NarrativeProvider(Protocol):
    def generate_explanation(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> str: ...

    def generate_recommendations(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> list[RecommendationItem]: ...


class RuleBasedNarrativeProvider:
    """English deterministic narrative from explainability + recommendation services."""

    def generate_explanation(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> str:
        return build_explanation(excavation, conflicts, risk)

    def generate_recommendations(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> list[RecommendationItem]:
        return recommend(risk, conflicts)


class LocationTemplateNarrativeProvider:
    """EN/AR template narrative for manual coordinate entry."""

    def __init__(
        self,
        payload: LocationAnalysisInput,
        infrastructure_overlaps: list[InfrastructureOverlapDetail],
        project_overlaps: list[ProjectOverlapDetail],
        temporal_overlaps: list[TemporalOverlapDetail],
    ) -> None:
        self._payload = payload
        self._infra = infrastructure_overlaps
        self._projects = project_overlaps
        self._temporal = temporal_overlaps

    def generate_explanation(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> str:
        return build_location_explanation(
            self._payload,
            risk.risk_score,
            risk.risk_level,
            self._infra,
            self._projects,
            self._temporal,
            self._payload.language,
        )

    def generate_recommendations(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> list[RecommendationItem]:
        return build_location_recommendations(
            risk.risk_level,
            self._infra,
            self._projects,
            self._temporal,
            self._payload,
            self._payload.language,
        )


class GeminiNarrativeProvider:
    """Google Gemini implementation (optional; raises GeminiServiceError on failure)."""

    def generate_explanation(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> str:
        return gemini_generate_explanation(excavation, conflicts, risk)

    def generate_recommendations(
        self,
        excavation: ExcavationRequest,
        conflicts: DetectedConflicts,
        risk: RiskResult,
    ) -> list[RecommendationItem]:
        return gemini_generate_recommendations(excavation, conflicts, risk)


def ai_narrative_enabled() -> bool:
    return narrative_layer_status() == "active"


def generate_narrative(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    risk: RiskResult,
    *,
    use_ai: bool,
    fallback: NarrativeProvider,
) -> tuple[str, list[RecommendationItem], NarrativeSource]:
    """
    Try Gemini when requested and configured; otherwise use the supplied fallback provider.
    """
    if use_ai and ai_narrative_enabled():
        gemini = GeminiNarrativeProvider()
        try:
            explanation = gemini.generate_explanation(excavation, conflicts, risk)
            recommendations = gemini.generate_recommendations(excavation, conflicts, risk)
            return explanation, recommendations, "gemini"
        except GeminiServiceError as exc:
            logger.warning("Gemini narrative fallback: %s", exc)
        except Exception:
            logger.exception("Gemini narrative fallback after unexpected error")

    explanation = fallback.generate_explanation(excavation, conflicts, risk)
    recommendations = fallback.generate_recommendations(excavation, conflicts, risk)
    source: NarrativeSource = (
        "location_template" if isinstance(fallback, LocationTemplateNarrativeProvider) else "deterministic"
    )
    return explanation, recommendations, source


def provider_name_from_env() -> str:
    return (os.getenv("NARRATIVE_PROVIDER") or "gemini").strip().lower()
