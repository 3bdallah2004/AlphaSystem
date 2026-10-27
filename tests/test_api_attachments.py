from fastapi.testclient import TestClient

import analysis
import extract
import vision
from api.main import app


def test_upload_list_download_range_and_delete_attachment(database, case):
    with TestClient(app) as client:
        uploaded = client.post(
            f"/api/cases/{case}/attachments",
            files=[("files", ("evidence.txt", b"0123456789", "text/plain"))],
        )
        assert uploaded.status_code == 200
        assert uploaded.json()["uploaded"] == 1
        attachment = uploaded.json()["attachments"][0]
        assert attachment["file_name"] == "evidence.txt"

        listing = client.get(f"/api/cases/{case}/attachments")
        assert listing.json()[0]["read_status"] == "will_read"

        file_response = client.get(f"/api/attachments/{attachment['id']}/file",
                                   headers={"Range": "bytes=0-3"})
        assert file_response.status_code == 206
        assert file_response.content == b"0123"

        deleted = client.delete(f"/api/attachments/{attachment['id']}")
        assert deleted.status_code == 204
        assert client.get(f"/api/attachments/{attachment['id']}/file").status_code == 404


def test_read_preview_describes_documents_and_images(database, case, monkeypatch):
    database.add_attachment(case, "image.png", f"{case}/image.png", "image/png", 1, "image")
    monkeypatch.setattr(extract, "describe", lambda *_args, **_kwargs: ("document text", [("image.png", "data:image/png;base64,AA==", 1)]))
    monkeypatch.setattr(vision, "describe_many", lambda *_args, **_kwargs: ("image description", []))
    with TestClient(app) as client:
        response = client.post(f"/api/cases/{case}/attachments/read-preview")
    assert response.status_code == 200
    assert response.json() == {"text": "document text\n\nimage description", "errors": []}


def test_case_delete_removes_attachment_metadata_and_file(database, case):
    with TestClient(app) as client:
        uploaded = client.post(
            f"/api/cases/{case}/attachments",
            files=[("files", ("delete-me.txt", b"secret-free test content", "text/plain"))],
        )
        attachment_id = uploaded.json()["attachments"][0]["id"]
        response = client.delete(f"/api/cases/{case}")
    assert response.status_code == 204
    assert database.get_case(case) is None
    assert database.get_attachment(attachment_id) is None


def test_upload_to_analyzed_case_starts_fresh_analysis(database, case, monkeypatch):
    database.update_case(case, status="analyzed", report_text='{"summary":"old"}')
    started = []
    monkeypatch.setattr(analysis, "start_analysis", lambda case_id, lang: started.append((case_id, lang)))
    with TestClient(app) as client:
        response = client.post(
            f"/api/cases/{case}/attachments?reanalyze=true&lang=en",
            files=[("files", ("new-evidence.txt", b"new evidence", "text/plain"))],
        )
    assert response.status_code == 200
    assert response.json()["uploaded"] == 1
    assert started == [(case, "en")]


def test_editor_can_defer_reanalysis_until_case_changes_are_saved(database, case, monkeypatch):
    database.update_case(case, status="analyzed", report_text='{"summary":"old"}')
    started = []
    monkeypatch.setattr(analysis, "start_analysis", lambda case_id, lang: started.append(case_id))
    with TestClient(app) as client:
        response = client.post(
            f"/api/cases/{case}/attachments?reanalyze=false",
            files=[("files", ("new-evidence.txt", b"new evidence", "text/plain"))],
        )
    assert response.status_code == 200
    assert response.json()["uploaded"] == 1
    assert started == []
