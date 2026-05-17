"""
Unified analysis pipeline: conflicts → risk score → optional AI narrative.
"""

from __future__ import annotations

from models import (
    AnalyzeResponse,
    DetectedConflicts,
    ExcavationRequest,
    HistoricalIncident,
    InfrastructureAsset,
    LocationAnalysisInput,
    LocationAnalysisResponse,
    Project,
    RecommendationItem,
    RiskResult,
)
from config.demo_neighborhood import is_point_inside_demo_area, neighborhood_context
from demo.synthetic_context import generate_local_synthetic_context
from services.conflict_detection import detect_conflicts
from services.location_narrative import risk_level_label
from services.narrative_provider import (
    LocationTemplateNarrativeProvider,
    RuleBasedNarrativeProvider,
    generate_narrative,
)
from services.overlap_summaries import collect_overlap_summaries
from services.risk_scoring import compute_risk


MANUAL_REQUEST_ID = "MANUAL-LOCATION"


def location_input_to_excavation(payload: LocationAnalysisInput) -> ExcavationRequest:
    return ExcavationRequest(
        request_id=MANUAL_REQUEST_ID,
        latitude=payload.latitude,
        longitude=payload.longitude,
        depth=payload.depth,
        radius_meters=payload.work_radius,
        start_date=payload.start_date,
        end_date=payload.end_date,
        excavation_type="Manual entry",
        contractor_name="POC",
    )


def run_core_analysis(
    excavation: ExcavationRequest,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> tuple[DetectedConflicts, RiskResult]:
    conflicts = detect_conflicts(excavation, infrastructure, projects)
    risk = compute_risk(excavation, conflicts, infrastructure, projects, incidents)
    return conflicts, risk


def run_excavation_analysis(
    excavation: ExcavationRequest,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
    *,
    use_ai_narrative: bool = True,
) -> AnalyzeResponse:
    conflicts, risk = run_core_analysis(excavation, infrastructure, projects, incidents)
    fallback = RuleBasedNarrativeProvider()
    explanation, recommendations, _source = generate_narrative(
        excavation,
        conflicts,
        risk,
        use_ai=use_ai_narrative,
        fallback=fallback,
    )
    return AnalyzeResponse(
        excavation=excavation,
        conflicts=conflicts,
        risk=risk,
        explanation=explanation,
        recommendations=recommendations,
    )


def run_manual_location_analysis(
    payload: LocationAnalysisInput,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> LocationAnalysisResponse:
    if payload.use_synthetic_context:
        ctx_assets, ctx_projects, ctx_incidents = generate_local_synthetic_context(payload)
        analysis_infrastructure = [*ctx_assets, *infrastructure]
        analysis_projects = [*ctx_projects, *projects]
        analysis_incidents = [*ctx_incidents, *incidents]
    else:
        analysis_infrastructure = list(infrastructure)
        analysis_projects = list(projects)
        analysis_incidents = list(incidents)

    excavation = location_input_to_excavation(payload)
    conflicts, risk = run_core_analysis(excavation, analysis_infrastructure, analysis_projects, analysis_incidents)

    (
        infrastructure_overlaps,
        project_overlaps,
        temporal_overlaps,
        context_infrastructure,
        context_projects,
        context_incidents,
    ) = collect_overlap_summaries(payload, analysis_infrastructure, analysis_projects, analysis_incidents)

    fallback = LocationTemplateNarrativeProvider(
        payload,
        infrastructure_overlaps,
        project_overlaps,
        temporal_overlaps,
    )
    explanation, recommendations, narrative_source = generate_narrative(
        excavation,
        conflicts,
        risk,
        use_ai=payload.use_ai_narrative,
        fallback=fallback,
    )

    return LocationAnalysisResponse(
        input=payload,
        risk_score=risk.risk_score,
        risk_level=risk.risk_level,
        risk_level_label=risk_level_label(risk.risk_level, payload.language),
        is_risky=risk.risk_level != "Low",
        detected_conflicts=conflicts,
        context_infrastructure=context_infrastructure,
        context_projects=context_projects,
        context_incidents=context_incidents,
        neighborhood_context=neighborhood_context(is_point_inside_demo_area(payload.latitude, payload.longitude)),
        project_overlaps=project_overlaps,
        infrastructure_overlaps=infrastructure_overlaps,
        temporal_overlaps=temporal_overlaps,
        explanation=explanation,
        recommendations=recommendations,
        confidence_score=risk.confidence_score,
        confidence_rationale=risk.confidence_rationale,
        contributing_factors=risk.contributing_factors,
        narrative_source=narrative_source,
    )
