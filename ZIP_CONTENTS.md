# Backend POC zip — contents and quick start

This archive is a **backend-only** reference package for the Excavation Risk Assessment Digital Twin POC.

---

## Included modules

```text
backend/
  main.py                 FastAPI app, routes, CORS
  models.py               Pydantic request/response schemas
  data_generator.py       Synthetic dataset builder
  requirements.txt        Runtime dependencies
  requirements-dev.txt    pytest + httpx
  runtime.txt             python-3.11.9 (Render)
  .env.example            Environment template (copy to .env)
  data/fake_data.json     Sample persisted dataset
  config/
    demo_neighborhood.py  Demo map bounds/labels (optional)
  demo/
    synthetic_context.py  Per-request demo assets (optional)
  services/
    analysis_pipeline.py  Unified detect → score → narrative
    conflict_detection.py Spatial/temporal conflicts
    risk_scoring.py       0–100 composite index
    explainability.py     English rule-based explanation
    recommendation.py     Rule-based recommendations
    narrative_provider.py Provider abstraction (Gemini + fallbacks)
    gemini_service.py     Google Gemini SDK integration
    location_analysis.py  Manual location entrypoint
    location_narrative.py   EN/AR template fallback copy
    overlap_summaries.py  Typed overlap rows for clients
  tests/                  Offline pytest suite

docs/RISK_SCORE_CALCULATION.md
BACKEND_HANDOFF.md
README.md
render.yaml               Render Blueprint (optional)
runtime.txt               Repo-root Python pin (monorepo)
.gitignore
```

**Not included:** `frontend/`, `.env`, `.venv/`, `node_modules/`, build caches, IDE folders.

---

## Run locally

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open Swagger: `http://127.0.0.1:8000/docs`

### Tests

```powershell
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

---

## API keys (Gemini / future OpenAI)

1. Copy `backend/.env.example` → `backend/.env` (never commit `.env`).
2. Set **`GEMINI_API_KEY`** for optional AI narrative on analyze endpoints.
3. Set **`GEMINI_DISABLED=true`** to force offline deterministic text only.

OpenAI is **not implemented** in this POC; extend `services/narrative_provider.py` when ready.

---

## Important environment variables

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Google AI key (server-side only) |
| `GEMINI_MODEL_NAME` | Default `gemini-2.5-flash` |
| `GEMINI_MAX_RETRIES` | Default `2` |
| `GEMINI_DISABLED` | `true` / `1` / `yes` disables Gemini |
| `NARRATIVE_PROVIDER` | Reserved (`gemini` today) |
| `ALLOWED_ORIGINS` | CORS origins (comma-separated); preferred |
| `FRONTEND_ORIGIN` | Alias for CORS if `ALLOWED_ORIGINS` unset |
| `ENVIRONMENT` | `production` → CORS uses configured origins only |

---

## Primary endpoint (Unity / integrations)

`POST /analyze-location` — returns `risk_score`, `detected_conflicts`, typed overlaps, `conflicts` (legacy flat list), explanation, and recommendations.

See **`BACKEND_HANDOFF.md`** for architecture and deployment notes.
