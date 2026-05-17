# Excavation Risk Assessment Digital Twin (POC)

Proof of concept for excavation risk screening: enter location and work details, get a **0–100 risk score**, conflicts, explanations, and recommendations. Includes a React dashboard (EN/AR) with a map for **An Narjis District, Riyadh** demo data.

**Important:** All data is synthetic. Scoring is rule-based, not calibrated for real operations.

---

## What it does

- Detects spatial and schedule conflicts with nearby utilities and projects
- Computes risk score, level (Low / Medium / High), and contributing factors
- Returns analyst explanation and mitigation recommendations
- Optional **Google Gemini** to polish narrative text (deterministic fallback always works)

**Pipeline:** `detect_conflicts` → `compute_risk` → optional AI narrative

---

## Quick start

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
copy .env.example .env
.\.venv\Scripts\python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

API docs: http://127.0.0.1:8000/docs

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173

### Tests

```powershell
cd backend
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest
```

---

## Main API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/analyze-location` | Primary — manual coordinates + work details |
| POST | `/analyze/{excavation_id}` | Analyze a stored excavation record |
| GET | `/health` | Liveness |
| GET | `/ai-narrative-status` | Gemini configured or not |

See Swagger (`/docs`) for full list.

**Example body** for `/analyze-location`:

```json
{
  "longitude": 46.676244,
  "latitude": 24.828315,
  "depth": 4.85,
  "work_radius": 17.6,
  "start_date": "2026-05-12",
  "end_date": "2026-06-19",
  "language": "en"
}
```

---

## Configuration

Copy `backend/.env.example` to `backend/.env`.

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | Optional — enables Gemini narrative |
| `GEMINI_DISABLED` | Set `true` to force offline mode |
| `ALLOWED_ORIGINS` or `FRONTEND_ORIGIN` | CORS for deployed UI |
| `ENVIRONMENT` | `production` for strict CORS |

---

## Project layout

```text
backend/     FastAPI + risk engine + optional Gemini
frontend/    React + Vite dashboard
docs/        Risk scoring reference
```

---

## More documentation

| Document | Contents |
|----------|----------|
| [BACKEND_HANDOFF.md](BACKEND_HANDOFF.md) | Backend reuse, Unity notes, deployment |
| [docs/RISK_SCORE_CALCULATION.md](docs/RISK_SCORE_CALCULATION.md) | How the 0–100 score is calculated |
| [ZIP_CONTENTS.md](ZIP_CONTENTS.md) | Backend-only zip package |

**Backend-only zip:** `.\scripts\create_backend_zip.ps1`

---

## Tech stack

FastAPI · Pydantic · React · Vite · Leaflet · optional `google-generativeai`

---

## License

Internal POC / demo use only.
