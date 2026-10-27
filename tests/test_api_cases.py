from fastapi.testclient import TestClient

import analysis
from api.main import app


def test_create_get_and_patch_case(database, monkeypatch):
    monkeypatch.setattr(analysis, "locate_missing", lambda *_args: False)
    with TestClient(app) as client:
        created = client.post("/api/cases", json={"case_text": "بلاغ تجريبي يتجاوز الحد الأدنى للطول."})
        assert created.status_code == 201
        case = created.json()
        assert case["case_number"].startswith("ALP-")

        detail = client.get(f"/api/cases/{case['id']}")
        assert detail.status_code == 200
        assert detail.json()["report"] is None
        assert detail.json()["report_raw"] == ""

        updated = client.patch(f"/api/cases/{case['id']}", json={
            "case_name": "عنوان القضية", "case_type": "سرقة",
        })
        assert updated.status_code == 200
        assert updated.json()["case"]["case_name"] == "عنوان القضية"
        assert updated.json()["duplicate_case_number"] is False


def test_case_creation_rejects_short_and_whitespace_only_text(database):
    with TestClient(app) as client:
        for text in ("قصير", " " * 25):
            response = client.post("/api/cases", json={"case_text": text})
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "invalid_request"


def test_patch_rejects_fields_outside_public_allowlist(database, case):
    with TestClient(app) as client:
        response = client.patch(f"/api/cases/{case}", json={"worker": "api"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_list_cases_includes_stats_attachments_and_starts_location_lookup(database, case, monkeypatch):
    database.add_attachment(case, "note.txt", f"{case}/note.txt", "text/plain", 12, "text")
    database.update_case(case, location="رام الله")
    calls = []
    monkeypatch.setattr(analysis, "locate_missing", lambda ids, lang: calls.append((ids, lang)))
    with TestClient(app) as client:
        response = client.get("/api/cases?q=تجريبية&lang=en")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["cases"][0]["attachment_count"] == 1
    assert body["cases"][0]["location"] == "رام الله"
    assert body["stats"]["total"] == 1
    assert body["stats"]["by_severity"] == [["unknown", 1]]
    assert body["stats"]["by_type_severity"] == [["عام", "unknown", 1]]
    assert calls == [([case], "en")]


def test_suggest_case_details_does_not_wait_for_geocoding(database, case, monkeypatch):
    suggestion = {"case_name": "Suggested title", "location": "Ramallah"}
    monkeypatch.setattr(analysis, "suggest_details", lambda *_args: suggestion)
    monkeypatch.setattr(
        "api.routes.cases.geocode.find",
        lambda *_args: (_ for _ in ()).throw(AssertionError("suggest must not geocode synchronously")),
    )
    with TestClient(app) as client:
        response = client.post(f"/api/cases/{case}/suggest")
    assert response.status_code == 200
    assert response.json() == suggestion


def test_case_detail_and_patch_return_localized_not_found(database):
    with TestClient(app) as client:
        response = client.get("/api/cases/999?lang=en")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "case_not_found"
    assert "not found" in response.json()["error"]["message"]
