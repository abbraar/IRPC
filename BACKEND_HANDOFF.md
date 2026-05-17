# Backend handoff

How to reuse this **FastAPI** backend as a reference for a new AI service (e.g. Unity integration).

---

## Architecture

```text
main.py
  → analysis_pipeline.py
      → detect_conflicts()     conflict_detection.py
      → compute_risk()         risk_scoring.py
      → generate_narrative()   narrative_provider.py
          → Gemini (optional)  gemini_service.py
          → fallback           explainability / recommendation / location_narrative
  → overlap_summaries.py       typed overlap rows for clients
  → demo/synthetic_context.py  optional per-request demo assets
  → config/demo_neighborhood.py demo map bounds (not used by scoring math)
```

**Rules compute the score.** Gemini only rewrites explanation and recommendations.

Scoring formulas: [docs/RISK_SCORE_CALCULATION.md](docs/RISK_SCORE_CALCULATION.md)

---

## Key modules

| Module | Role |
|--------|------|
| `analysis_pipeline.py` | Unified analyze flow |
| `conflict_detection.py` | Spatial + temporal conflicts |
| `risk_scoring.py` | 0–100 score, factors, confidence |
| `narrative_provider.py` | Provider abstraction + fallback |
| `gemini_service.py` | Google Gemini SDK |
| `location_analysis.py` | Entry for manual coordinates |
| `location_narrative.py` | EN/AR template text fallback |
| `overlap_summaries.py` | Typed overlap DTOs for map/UI |
| `data_generator.py` | Seed synthetic JSON dataset |

---

## API (for Unity / integrations)

| Method | Path | Notes |
|--------|------|--------|
| POST | `/analyze-location` | **Start here** — lat/lon, depth, radius, dates |
| POST | `/analyze/{excavation_id}` | Stored excavation + same pipeline |
| GET | `/health` | Liveness |
| GET | `/ai-narrative-status` | `active` / `fallback` / `disabled` |
| GET | `/infrastructure`, `/projects`, `/incidents` | Reference layers |
| POST | `/generate-data?seed=` | Regenerate demo JSON |

**Request** (`/analyze-location`):

```json
{
  "longitude": 46.676244,
  "latitude": 24.828315,
  "depth": 4.85,
  "work_radius": 17.6,
  "start_date": "2026-05-12",
  "end_date": "2026-06-19",
  "language": "en",
  "use_synthetic_context": true,
  "use_ai_narrative": true
}
```

**Response fields (new clients):**

- `risk_score`, `risk_level`, `contributing_factors`, `confidence_score`, `confidence_rationale`
- `detected_conflicts` — `{ spatial, temporal }` (typed)
- `infrastructure_overlaps`, `project_overlaps`, `temporal_overlaps` — typed rows
- `explanation`, `recommendations`, `narrative_source`
- `conflicts` — legacy flat list (still present for the React app)

OpenAPI: `/docs`

### Unity notes

- **Editor / standalone:** CORS usually not required.
- **WebGL:** set `ALLOWED_ORIGINS` to your player origin.
- Prefer `detected_conflicts` + typed overlaps over `conflicts`.
- Set `use_synthetic_context: false` when you supply real asset data (today: merge with GET layers or extend API).

---

## Environment

Copy `backend/.env.example` → `backend/.env` (never commit `.env`).

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Optional Gemini |
| `GEMINI_MODEL_NAME` | Default `gemini-2.5-flash` |
| `GEMINI_MAX_RETRIES` | Default `2` |
| `GEMINI_DISABLED` | `true` forces offline narrative |
| `ALLOWED_ORIGINS` / `FRONTEND_ORIGIN` | CORS origins |
| `ENVIRONMENT` | `production` = strict CORS |
| `NARRATIVE_PROVIDER` | Reserved (`gemini`; OpenAI later) |

### Run & test

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

---

## Extending AI providers

Add a class implementing the same two methods as `GeminiNarrativeProvider` in `narrative_provider.py`:

- `generate_explanation(excavation, conflicts, risk)`
- `generate_recommendations(excavation, conflicts, risk)`

Wire selection via `NARRATIVE_PROVIDER` when you add OpenAI or compatible APIs.

---

## Synthetic data

| What | Where |
|------|--------|
| Saved demo world | `backend/data/fake_data.json` |
| Regenerate | `POST /generate-data` or `data_generator.py` |
| Extra assets per analyze | `demo/synthetic_context.py` |
| Demo polygon labels | `config/demo_neighborhood.py` |

Scoring does not depend on demo geography; only optional context and `neighborhood_context` in responses do.

---

## Deploy (Render)

- Root directory: `backend`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Python: `backend/runtime.txt` (`python-3.11.9`) and `PYTHON_VERSION` in `render.yaml`

---

## Limitations

- JSON file store only (no PostGIS / auth)
- No chat-style `/assistant` endpoint
- `dashboard-summary` scans all excavations (demo cost)
- Default demo context often yields ~**Medium** scores (~61) for sample coordinates

---

## Backend-only zip

```powershell
.\scripts\create_backend_zip.ps1
```

Creates `excavation-risk-backend-poc.zip`. Details: [ZIP_CONTENTS.md](ZIP_CONTENTS.md).
