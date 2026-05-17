"""Manual location analysis — delegates to the unified analysis pipeline."""

from __future__ import annotations

from models import (
    HistoricalIncident,
    InfrastructureAsset,
    LocationAnalysisInput,
    LocationAnalysisResponse,
    Project,
)
from services.analysis_pipeline import run_manual_location_analysis

# Re-export for tests and backward compatibility.
from config.demo_neighborhood import is_point_inside_demo_area as is_point_inside_neighborhood  # noqa: F401


def analyze_manual_location(
    payload: LocationAnalysisInput,
    infrastructure: list[InfrastructureAsset],
    projects: list[Project],
    incidents: list[HistoricalIncident],
) -> LocationAnalysisResponse:
    return run_manual_location_analysis(payload, infrastructure, projects, incidents)
