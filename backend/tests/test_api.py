from datetime import date

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ai_narrative_status():
    response = client.get("/ai-narrative-status")
    assert response.status_code == 200
    assert response.json()["status"] in {"active", "fallback", "disabled"}


def test_analyze_location_returns_typed_overlaps_and_conflicts():
    response = client.post(
        "/analyze-location",
        json={
            "longitude": 46.676244,
            "latitude": 24.828315,
            "depth": 4.85,
            "work_radius": 17.6,
            "start_date": "2026-05-12",
            "end_date": "2026-06-19",
            "language": "en",
            "use_ai_narrative": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "risk_score" in body
    assert "detected_conflicts" in body
    assert "infrastructure_overlaps" in body
    assert "conflicts" in body
    assert isinstance(body["conflicts"], list)
    if body["infrastructure_overlaps"]:
        assert "asset_id" in body["infrastructure_overlaps"][0]
    assert body["narrative_source"] == "location_template"


def test_analyze_location_rejects_invalid_dates():
    response = client.post(
        "/analyze-location",
        json={
            "longitude": 46.676244,
            "latitude": 24.828315,
            "depth": 2.0,
            "work_radius": 10.0,
            "start_date": "2026-06-19",
            "end_date": "2026-05-12",
            "language": "en",
        },
    )
    assert response.status_code == 400
