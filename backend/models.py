"""Pydantic models for excavation digital twin POC. Replace with DB schemas when wiring real data."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, computed_field


# --- Core entities (synthetic / future real API shapes) ---


class ExcavationRequest(BaseModel):
    request_id: str
    latitude: float
    longitude: float
    depth: float = Field(description="Excavation depth in meters")
    radius_meters: float
    start_date: date
    end_date: date
    excavation_type: str
    contractor_name: str


class InfrastructureAsset(BaseModel):
    asset_id: str
    type: Literal["Gas Pipeline", "Water Pipe", "Electrical Cable", "Telecom Line"]
    latitude: float
    longitude: float
    depth: float
    criticality: Literal["Low", "Medium", "High"]
    influence_radius: float = Field(default=8.0, description="Synthetic influence radius in meters")
    sensitivity_score: float = Field(ge=0, le=100)


class Project(BaseModel):
    project_id: str
    name: str
    latitude: float
    longitude: float
    radius_meters: float = Field(default=25.0, description="Synthetic project footprint radius")
    start_date: date
    end_date: date
    status: str


class HistoricalIncident(BaseModel):
    incident_id: str
    latitude: float
    longitude: float
    incident_type: str
    severity: Literal["Low", "Medium", "High", "Critical"]
    related_asset_type: str


# --- Analysis outputs ---


class SpatialConflict(BaseModel):
    kind: Literal["infrastructure", "project_site"]
    target_id: str
    target_name: str
    distance_meters: float
    severity: Literal["Low", "Medium", "High"]


class TemporalConflict(BaseModel):
    kind: Literal["schedule_overlap"]
    project_id: str
    project_name: str
    overlap_days: int
    severity: Literal["Low", "Medium", "High"]


class DetectedConflicts(BaseModel):
    spatial: list[SpatialConflict]
    temporal: list[TemporalConflict]


FactorCategory = Literal["Geometry", "Buried utilities", "Coordination", "History"]


class ContributingFactor(BaseModel):
    """Single line-item in the rule-based risk register (analyst-facing)."""

    factor: str = Field(description="Stable machine id, e.g. geometry_depth, utility_proximity")
    display_name: str = Field(description="Short label for reports and UI")
    category: FactorCategory
    weight_contribution: float = Field(ge=0, description="Points toward the 0–100 composite (pre-cap)")
    pct_of_composite: float = Field(
        ge=0,
        le=100,
        description="Share of the pre-cap composite sum from this line (sums ~100% before cap)",
    )
    detail: str = Field(description="Numeric, auditable rationale for this line")


class RiskResult(BaseModel):
    risk_score: float = Field(ge=0, le=100)
    risk_level: Literal["Low", "Medium", "High"]
    contributing_factors: list[ContributingFactor]
    confidence_score: float = Field(ge=0, le=1, description="Heuristic certainty in this assessment 0–1")
    confidence_rationale: str = Field(
        default="",
        description="One paragraph: what strengthened or limited confidence (rule-based, no calibration)",
    )


class RecommendationItem(BaseModel):
    action: str
    reasoning: str
    priority: Literal["low", "medium", "high"]


class AnalyzeResponse(BaseModel):
    excavation: ExcavationRequest
    conflicts: DetectedConflicts
    risk: RiskResult
    explanation: str
    recommendations: list[RecommendationItem]


class LocationAnalysisInput(BaseModel):
    """
    Manual analysis input (WGS84 coordinates).

    latitude is north/south; longitude is east/west.
    """

    longitude: float
    latitude: float
    depth: float = Field(gt=0)
    work_radius: float = Field(gt=0)
    start_date: date
    end_date: date
    language: Literal["en", "ar"] = "en"
    use_synthetic_context: bool = Field(
        default=True,
        description="When true, merge demo synthetic assets/projects/incidents around the coordinate.",
    )
    use_ai_narrative: bool = Field(
        default=True,
        description="When true, attempt Gemini narrative if configured; always falls back deterministically.",
    )


class InfrastructureOverlapDetail(BaseModel):
    asset_id: str
    type: str
    latitude: float
    longitude: float
    distance_meters: float
    asset_depth: float
    criticality: str
    influence_radius: float
    sensitivity_score: float
    depth_conflict: bool
    severity: Literal["Low", "Medium", "High"]


class ProjectOverlapDetail(BaseModel):
    project_id: str
    name: str
    latitude: float
    longitude: float
    distance_meters: float
    radius_meters: float
    status: str
    severity: Literal["Low", "Medium", "High"]
    has_temporal_overlap: bool
    overlap_days: int


class TemporalOverlapDetail(BaseModel):
    project_id: str
    name: str
    start_date: str
    end_date: str
    overlap_days: int
    spatial_overlap: bool
    severity: Literal["Low", "Medium", "High"]


class LocationAnalysisResponse(BaseModel):
    input: LocationAnalysisInput
    risk_score: float = Field(ge=0, le=100)
    risk_level: Literal["Low", "Medium", "High"]
    risk_level_label: str
    is_risky: bool
    detected_conflicts: DetectedConflicts
    context_infrastructure: list[InfrastructureAsset] = Field(default_factory=list)
    context_projects: list[Project] = Field(default_factory=list)
    context_incidents: list[HistoricalIncident] = Field(default_factory=list)
    neighborhood_context: dict[str, Any] = Field(default_factory=dict)
    project_overlaps: list[ProjectOverlapDetail]
    infrastructure_overlaps: list[InfrastructureOverlapDetail]
    temporal_overlaps: list[TemporalOverlapDetail]
    explanation: str
    recommendations: list[RecommendationItem]
    confidence_score: float = Field(default=0.75, ge=0, le=1)
    confidence_rationale: str = ""
    contributing_factors: list[ContributingFactor] = Field(default_factory=list)
    narrative_source: Literal["gemini", "deterministic", "location_template"] = "deterministic"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def conflicts(self) -> list[dict[str, Any]]:
        """Legacy flattened conflict list (kind + overlap fields) for existing web clients."""
        return [
            *[{"kind": "infrastructure", **item.model_dump(mode="json")} for item in self.infrastructure_overlaps],
            *[{"kind": "project", **item.model_dump(mode="json")} for item in self.project_overlaps],
            *[{"kind": "temporal", **item.model_dump(mode="json")} for item in self.temporal_overlaps],
        ]


class DashboardSummary(BaseModel):
    total_requests: int
    high_risk_count: int
    medium_risk_count: int
    low_risk_count: int
    last_analyzed_at: str | None = None


class FakeDataStore(BaseModel):
    """Root document persisted as JSON. Easy to swap for DB rows later."""

    excavations: list[ExcavationRequest]
    infrastructure: list[InfrastructureAsset]
    projects: list[Project]
    incidents: list[HistoricalIncident]

    model_config = {"extra": "ignore"}


class GenerateDataResponse(BaseModel):
    message: str
    counts: dict[str, int]
