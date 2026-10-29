from fastapi.testclient import TestClient

import chat
import db
from api.main import app


def test_list_messages_includes_attachments(database):
    message_id = database.add_message(chat.GLOBAL_CHAT, "user", "سؤال")
    database.add_attachment(chat.GLOBAL_CHAT, "context.txt", "0/context.txt", "text/plain", 1, "text",
                            message_id=message_id)
    with TestClient(app) as client:
        response = client.get("/api/chat/messages")
    assert response.status_code == 200
    assert response.json()[0]["attachments"][0]["file_name"] == "context.txt"


def test_send_message_starts_reply_and_accepts_upload(database, case, monkeypatch):
    saved = {}

    def fake_ask(text, lang, files, focus_case_id=None, request_id=None):
        saved.update(text=text, lang=lang, files=files, focus_case_id=focus_case_id)
        return 12, 13, len(files), []

    monkeypatch.setattr(chat, "ask", fake_ask)
    with TestClient(app) as client:
        response = client.post(
            "/api/chat/messages?lang=en",
            data={"text": "follow up", "case_id": str(case)},
            files=[("files", ("note.txt", b"new evidence", "text/plain"))],
        )
    assert response.status_code == 202
    assert response.json()["reply_id"] == 13
    assert saved["lang"] == "en"
    assert saved["focus_case_id"] == case
    assert saved["files"][0].name == "note.txt"
    assert saved["files"][0].getvalue() == b"new evidence"


def test_send_message_without_an_open_case(database, monkeypatch):
    saved = {}
    monkeypatch.setattr(chat, "ask", lambda text, lang, files, focus_case_id=None, request_id=None:
                        saved.update(focus_case_id=focus_case_id) or (1, 2, 0, []))
    with TestClient(app) as client:
        response = client.post("/api/chat/messages", data={"text": "how many thefts?"})
    assert response.status_code == 202
    assert saved["focus_case_id"] is None


def test_send_message_rejects_an_unknown_case(database, monkeypatch):
    monkeypatch.setattr(chat, "ask", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("called")))
    with TestClient(app) as client:
        response = client.post("/api/chat/messages", data={"text": "q", "case_id": "999"})
    assert response.status_code == 404


def test_send_message_rejects_an_empty_message(database):
    with TestClient(app) as client:
        response = client.post("/api/chat/messages", data={"text": "  "})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "empty_message"


def test_retry_only_accepts_failed_assistant_replies(database, monkeypatch):
    failed_reply = db.add_message(chat.GLOBAL_CHAT, "assistant", "failed", status="failed")
    user_message = db.add_message(chat.GLOBAL_CHAT, "user", "question")
    retried = []
    monkeypatch.setattr(chat, "retry", lambda msg_id, lang: retried.append(msg_id))
    with TestClient(app) as client:
        response = client.post(f"/api/messages/{failed_reply}/retry")
        invalid = client.post(f"/api/messages/{user_message}/retry")
    assert response.status_code == 202
    assert invalid.status_code == 422
    assert retried == [failed_reply]


def test_clear_messages_uses_core_chat_logic(database, monkeypatch):
    calls = []
    monkeypatch.setattr(chat, "clear", lambda: calls.append(True))
    with TestClient(app) as client:
        response = client.delete("/api/chat/messages")
    assert response.status_code == 204
    assert calls == [True]
