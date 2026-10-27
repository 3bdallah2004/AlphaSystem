from fastapi.testclient import TestClient

import geocode
from api.main import app


def test_meta_health_samples_and_geocode(database, monkeypatch):
    monkeypatch.setattr("analysis.check_n8n", lambda lang: ("success", f"ready:{lang}"))
    monkeypatch.setattr(geocode, "find", lambda query, lang: (31.9, 35.2) if query == "Jenin" else None)
    with TestClient(app) as client:
        metadata = client.get("/api/meta")
        health = client.get("/api/health?lang=en")
        samples = client.get("/api/samples?lang=en")
        found = client.get("/api/geocode?q=Jenin&lang=en")
        missing = client.get("/api/geocode?q=unknown&lang=en")
    assert metadata.json()["max_attachment_mb"] > 0
    assert health.json() == {"level": "success", "message": "ready:en"}
    assert samples.json()[0]["text"]
    assert found.json() == {"latitude": 31.9, "longitude": 35.2}
    assert missing.json() is None


def test_about_assets_are_allowlisted(database):
    with TestClient(app) as client:
        video = client.get("/api/assets/about-video-user.mp4")
        removed_poster = client.get("/api/assets/about-video-poster.jpg")
        denied = client.get("/api/assets/alpha_database.db")
    assert video.status_code == 200
    assert video.headers["content-type"] == "video/mp4"
    assert removed_poster.status_code == 404
    assert denied.status_code == 404
