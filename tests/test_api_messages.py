from fastapi.testclient import TestClient

import chat
import db
from api.main import app


def test_list_messages_includes_attachments(database, case):
    message_id = database.add_message(case, "user", "سؤال")
    database.add_attachment(case, "context.txt", f"{case}/context.txt", "text/plain", 1, "text",
                            message_id=message_id)
    with TestClient(app) as client:
        response = client.get(f"/api/cases/{case}/messages")
    assert response.status_code == 200
    assert response.json()[0]["attachments"][0]["file_name"] == "context.txt"


def test_send_message_starts_reply_and_accepts_upload(database, case, monkeypatch):
    saved = {}

    def fake_ask(case_id, text, lang, files):
        saved.update(case_id=case_id, text=text, lang=lang, files=files)
        return 12, 13, len(files), []

    monkeypatch.setattr(chat, "ask", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            f"/api/cases/{case}/messages?lang=en",
            data={"text": "follow up"},
            files=[("files", ("note.txt", b"new evidence", "text/plain"))],
        )
    assert response.status_code == 202
    assert response.json()["reply_id"] == 13
    assert saved["lang"] == "en"
    assert saved["files"][0].name == "note.txt"
    assert saved["files"][0].getvalue() == b"new evidence"


def test_retry_only_accepts_failed_assistant_replies(database, case, monkeypatch):
    failed_reply = db.add_message(case, "assistant", "failed", status="failed")
    user_message = db.add_message(case, "user", "question")
    retried = []
    monkeypatch.setattr(chat, "retry", lambda case_id, msg_id, lang: retried.append(msg_id))
    with TestClient(app) as client:
        response = client.post(f"/api/messages/{failed_reply}/retry")
        invalid = client.post(f"/api/messages/{user_message}/retry")
    assert response.status_code == 202
    assert invalid.status_code == 422
    assert retried == [failed_reply]


def test_update_report_requires_completed_reply(database, case):
    pending = database.add_message(case, "assistant", "", status="pending")
    with TestClient(app) as client:
        response = client.post(f"/api/messages/{pending}/update-report")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "reply_not_complete"


def test_clear_messages_uses_core_chat_logic(database, case, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "clear", lambda case_id: calls.append(case_id))
    with TestClient(app) as client:
        response = client.delete(f"/api/cases/{case}/messages")
    assert response.status_code == 204
    assert calls == [case]
