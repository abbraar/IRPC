"""
FastAPI entrypoint for Excavation Risk Assessment Digital Twin POC.

Persistence: JSON file under data/fake_data.json (easy swap for SQLite/PostGIS later).
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent / ".env")

from data_generator import generate_fake_data, load_store, save_store
from models import (
    AnalyzeResponse,
    DashboardSummary,
    ExcavationRequest,
    FakeDataStore,
    GenerateDataResponse,
    LocationAnalysisInput,
    LocationAnalysisResponse,
)
from services.conflict_detection import detect_conflicts
from services.explainability import build_explanation
from services.gemini_service import (
    GeminiServiceError,
    generate_explanation,
    generate_recommendations,
    narrative_layer_status,
)
from services.location_analysis import analyze_manual_location
from services.recommendation import recommend
from services.risk_scoring import compute_risk

DATA_PATH = Path(__file__).resolve().parent / "data" / "fake_data.json"
logger = logging.getLogger(__name__)

_LOCAL_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def _parse_csv_origins(value: str) -> list[str]:
    origins: list[str] = []
    for part in value.split(","):
        p = part.strip().rstrip("/")
        if p:
            origins.append(p)
    return origins


def _cors_allow_origins() -> list[str]:
    environment = (os.environ.get("ENVIRONMENT") or "").strip().lower()
    configured = _parse_csv_origins(os.environ.get("FRONTEND_ORIGIN") or "")
    if environment == "production":
        if not configured:
            logger.warning(
                "ENVIRONMENT=production but FRONTEND_ORIGIN is empty; "
                "browser clients on another origin will fail CORS until it is set."
            )
        return configured
    merged: list[str] = []
    seen: set[str] = set()
    for o in configured + _LOCAL_DEV_ORIGINS:
        if o not in seen:
            seen.add(o)
            merged.append(o)
    return merged


app = FastAPI(title="Excavation Risk Digital Twin", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_store: FakeDataStore | None = None
_last_analyzed_at: str | None = None


def get_store() -> FakeDataStore:
    global _store
    if _store is None:
        loaded = load_store(DATA_PATH)
        if loaded:
            _store = loaded
        else:
            _store = generate_fake_data()
            save_store(DATA_PATH, _store)
    return _store


@app.get("/excavations", response_model=list[ExcavationRequest])
def list_excavations() -> list[ExcavationRequest]:
    return get_store().excavations


@app.get("/excavations/{excavation_id}", response_model=ExcavationRequest)
def get_excavation(excavation_id: str) -> ExcavationRequest:
    for e in get_store().excavations:
        if e.request_id == excavation_id:
            return e
    logger.warning("API error: excavation not found (id=%s)", excavation_id)
    raise HTTPException(status_code=404, detail="Excavation not found")


@app.get("/infrastructure")
def list_infrastructure():
    return get_store().infrastructure


@app.get("/projects")
def list_projects():
    return get_store().projects


@app.get("/incidents")
def list_incidents():
    return get_store().incidents


@app.post("/analyze/{excavation_id}", response_model=AnalyzeResponse)
def analyze(excavation_id: str) -> AnalyzeResponse:
    global _last_analyzed_at
    store = get_store()
    excavation = next((e for e in store.excavations if e.request_id == excavation_id), None)
    if not excavation:
        logger.warning("API error: analyze requested for unknown excavation (id=%s)", excavation_id)
        raise HTTPException(status_code=404, detail="Excavation not found")

    conflicts = detect_conflicts(excavation, store.infrastructure, store.projects)
    risk = compute_risk(excavation, conflicts, store.infrastructure, store.projects, store.incidents)

    try:
        explanation = generate_explanation(excavation, conflicts, risk)
        recommendations = generate_recommendations(excavation, conflicts, risk)
    except GeminiServiceError as exc:
        logger.warning("Gemini fallback triggered for %s: %s", excavation_id, exc)
        explanation = build_explanation(excavation, conflicts, risk)
        recommendations = recommend(risk, conflicts)
    except Exception as exc:
        logger.exception("Gemini fallback triggered after unexpected API error for %s: %s", excavation_id, exc)
        explanation = build_explanation(excavation, conflicts, risk)
        recommendations = recommend(risk, conflicts)

    _last_analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    return AnalyzeResponse(
        excavation=excavation,
        conflicts=conflicts,
        risk=risk,
        explanation=explanation,
        recommendations=recommendations,
    )


@app.post("/analyze-location", response_model=LocationAnalysisResponse)
def analyze_location(payload: LocationAnalysisInput, lang: Literal["en", "ar"] | None = None) -> LocationAnalysisResponse:
    global _last_analyzed_at
    store = get_store()
    if payload.start_date > payload.end_date:
        logger.warning("API error: invalid manual location schedule")
        raise HTTPException(status_code=400, detail="start_date must be before or equal to end_date")
    if lang:
        payload = payload.model_copy(update={"language": lang})
    result = analyze_manual_location(payload, store.infrastructure, store.projects, store.incidents)
    _last_analyzed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return result


def _risk_level_for_excavation(exc: ExcavationRequest) -> str:
    store = get_store()
    c = detect_conflicts(exc, store.infrastructure, store.projects)
    r = compute_risk(exc, c, store.infrastructure, store.projects, store.incidents)
    return r.risk_level


@app.get("/dashboard-summary", response_model=DashboardSummary)
def dashboard_summary() -> DashboardSummary:
    store = get_store()
    high = medium = low = 0
    for exc in store.excavations:
        lvl = _risk_level_for_excavation(exc)
        if lvl == "High":
            high += 1
        elif lvl == "Medium":
            medium += 1
        else:
            low += 1
    return DashboardSummary(
        total_requests=len(store.excavations),
        high_risk_count=high,
        medium_risk_count=medium,
        low_risk_count=low,
        last_analyzed_at=_last_analyzed_at,
    )


@app.post("/generate-data", response_model=GenerateDataResponse)
def generate_data(seed: int = 42) -> GenerateDataResponse:
    global _store, _last_analyzed_at
    _last_analyzed_at = None
    _store = generate_fake_data(seed=seed)
    save_store(DATA_PATH, _store)
    return GenerateDataResponse(
        message="Synthetic dataset regenerated and saved.",
        counts={
            "excavations": len(_store.excavations),
            "infrastructure": len(_store.infrastructure),
            "projects": len(_store.projects),
            "incidents": len(_store.incidents),
        },
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ai-narrative-status")
def ai_narrative_status():
    status = narrative_layer_status()
    return {"status": status}
