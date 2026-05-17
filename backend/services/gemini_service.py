"""
Gemini language-generation layer for the excavation risk POC.

Important architecture boundary:
- Gemini does NOT detect conflicts.
- Gemini does NOT calculate risk score, risk level, confidence, or contributing factors.
- Gemini only rewrites analyst narrative and recommendations from rule-engine outputs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
import time
from typing import Any

from dotenv import load_dotenv

try:
    import google.generativeai as genai
except ImportError:  # keeps the app importable; requests will fall back cleanly
    genai = None  # type: ignore[assignment]

from models import (
    DetectedConflicts,
    ExcavationRequest,
    RecommendationItem,
    RiskResult,
)

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = "gemini-2.5-flash"
MODEL_NAME = os.getenv("GEMINI_MODEL_NAME", DEFAULT_MODEL_NAME)
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))

_TEXT_CACHE: dict[str, str] = {}
_RECOMMENDATION_CACHE: dict[str, list[RecommendationItem]] = {}

ALLOWED_ACTIONS = {
    "Proceed",
    "Proceed with caution",
    "Reschedule",
    "Reroute",
    "Manual review required",
}
ACTION_ALIASES = {
    "manual review": "Manual review required",
    "manual review required": "Manual review required",
    "proceed": "Proceed",
    "proceed with caution": "Proceed with caution",
    "reschedule": "Reschedule",
    "reroute": "Reroute",
    "re-route": "Reroute",
}
PRIORITY_MAP = {"LOW": "low", "MEDIUM": "medium", "HIGH": "high"}


class GeminiServiceError(RuntimeError):
    """Raised when Gemini is unavailable or returns unusable content."""


def narrative_layer_status() -> str:
    """Lightweight status for UI display; never calls the external API."""
    if os.getenv("GEMINI_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return "disabled"
    if genai is not None and os.getenv("GEMINI_API_KEY"):
        return "active"
    return "fallback"


def _get_model():
    if genai is None:
        raise GeminiServiceError("google-generativeai package is not installed")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise GeminiServiceError("GEMINI_API_KEY is not configured")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(MODEL_NAME)


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _compact_context(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    risk: RiskResult,
) -> dict[str, Any]:
    """
    Token-safe context for Gemini. Only pass structured facts from the deterministic
    engine; trim long factor detail strings so prompts stay bounded.
    """
    risk_dict = risk.model_dump(mode="json")
    risk_dict["contributing_factors"] = [
        {
            "factor": f.factor,
            "display_name": f.display_name,
            "category": f.category,
            "weight_contribution": f.weight_contribution,
            "pct_of_composite": f.pct_of_composite,
            "detail": f.detail[:420],
        }
        for f in sorted(
            risk.contributing_factors,
            key=lambda item: item.weight_contribution,
            reverse=True,
        )
    ]
    return {
        "excavation": excavation.model_dump(mode="json"),
        "conflicts": conflicts.model_dump(mode="json"),
        "risk": risk_dict,
    }


def _cache_key(kind: str, payload: dict[str, Any]) -> str:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(f"{kind}:{MODEL_NAME}:{body}".encode("utf-8")).hexdigest()


def _extract_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if text:
        return str(text).strip()

    # Defensive fallback for SDK response variants.
    try:
        parts = response.candidates[0].content.parts
        return "".join(getattr(p, "text", "") for p in parts).strip()
    except Exception as exc:  # pragma: no cover - depends on SDK response internals
        raise GeminiServiceError("Gemini returned an empty response") from exc


def _strip_json_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```json").removeprefix("```").strip()
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    return cleaned


def _generate_json(prompt: str, *, max_output_tokens: int = 1800) -> Any:
    logger.info("Gemini request started (model=%s)", MODEL_NAME)
    model = _get_model()
    last_error: Exception | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    temperature=0.2,
                    max_output_tokens=max_output_tokens,
                    response_mime_type="application/json",
                ),
            )
            raw = _extract_text(response)
            logger.info("Gemini response success (attempt=%s)", attempt)
            return json.loads(_strip_json_fence(raw))
        except Exception as exc:  # external API can fail in many ways
            last_error = exc
            logger.warning("Gemini request failed (attempt=%s): %s", attempt, exc)
            if attempt < MAX_RETRIES:
                time.sleep(0.6 * attempt)
    raise GeminiServiceError(f"Gemini request failed after {MAX_RETRIES} attempt(s)") from last_error


def _normalise_action(value: Any) -> str | None:
    text = str(value or "").strip()
    if text in ALLOWED_ACTIONS:
        return text
    return ACTION_ALIASES.get(text.lower())


def _normalise_priority(value: Any) -> str:
    return PRIORITY_MAP.get(str(value or "").strip().upper(), "medium")


def generate_recommendations(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    risk: RiskResult,
) -> list[RecommendationItem]:
    """
    Ask Gemini for professional recommendation wording, then validate it back into
    the unchanged API schema. Raises GeminiServiceError if output is unusable.
    """
    context = _compact_context(excavation, conflicts, risk)
    key = _cache_key("recommendations", context)
    if key in _RECOMMENDATION_CACHE:
        logger.info("Gemini recommendation cache hit")
        return _RECOMMENDATION_CACHE[key]

    prompt = f"""
You are an excavation risk analyst writing mitigation recommendations.

Use ONLY the JSON context below. Do NOT invent infrastructure, incidents, dates,
assets, locations, conflicts, or risk causes. The deterministic rule engine is
the source of truth for risk score, risk level, confidence, conflicts, and factors.
You must not recalculate or modify those values.

Return JSON only. Return 3 to 5 objects. Each object must contain:
- action: one of ["Proceed", "Proceed with caution", "Reschedule", "Reroute", "Manual review required"]
- reasoning: professional engineering-oriented explanation grounded only in the provided context
- priority: one of ["LOW", "MEDIUM", "HIGH"]

Context:
{json.dumps(context, indent=2)}
"""
    data = _generate_json(prompt, max_output_tokens=1600)
    if not isinstance(data, list):
        raise GeminiServiceError("Gemini recommendations response was not a JSON array")

    items: list[RecommendationItem] = []
    for row in data[:5]:
        if not isinstance(row, dict):
            continue
        action = _normalise_action(row.get("action"))
        reasoning = str(row.get("reasoning", "")).strip()
        if not action or not reasoning:
            continue
        items.append(
            RecommendationItem(
                action=action,  # type: ignore[arg-type]
                reasoning=reasoning[:900],
                priority=_normalise_priority(row.get("priority")),  # type: ignore[arg-type]
            )
        )

    if len(items) < 3:
        raise GeminiServiceError("Gemini returned fewer than 3 valid recommendations")
    _RECOMMENDATION_CACHE[key] = items
    return items


def generate_explanation(
    excavation: ExcavationRequest,
    conflicts: DetectedConflicts,
    risk: RiskResult,
) -> str:
    """
    Ask Gemini for an analyst-style narrative using the existing section structure.
    Raises GeminiServiceError if the response is missing required sections.
    """
    context = _compact_context(excavation, conflicts, risk)
    key = _cache_key("explanation", context)
    if key in _TEXT_CACHE:
        logger.info("Gemini explanation cache hit")
        return _TEXT_CACHE[key]

    prompt = f"""
You are an excavation risk analyst. Write a concise, professional desk-review
narrative from the provided deterministic rule-engine output.

Rules:
- Use ONLY the JSON context below.
- Do NOT invent infrastructure, incidents, projects, conflicts, measurements, dates, or causes.
- Do NOT recalculate the risk score, risk level, confidence score, or contributing factors.
- Keep these exact section headers, in this exact order:
  ASSESSMENT SUMMARY
  CONFLICT REGISTER
  PRIMARY CONTRIBUTORS
  ANALYST GUIDANCE
- Use short paragraphs and bullet lines beginning with "•" where useful.
- Mention that this is synthetic/demo data when giving operational guidance.

Return JSON only with this schema:
{{"explanation": "ASSESSMENT SUMMARY\\n..."}}

Context:
{json.dumps(context, indent=2)}
"""
    data = _generate_json(prompt, max_output_tokens=2200)
    if not isinstance(data, dict):
        raise GeminiServiceError("Gemini explanation response was not a JSON object")
    explanation = str(data.get("explanation", "")).strip()
    required = [
        "ASSESSMENT SUMMARY",
        "CONFLICT REGISTER",
        "PRIMARY CONTRIBUTORS",
        "ANALYST GUIDANCE",
    ]
    if not explanation or any(section not in explanation for section in required):
        raise GeminiServiceError("Gemini explanation is missing required sections")
    _TEXT_CACHE[key] = explanation
    return explanation
