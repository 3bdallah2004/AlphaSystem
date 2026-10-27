"""The per-case conversation: history, payload building, asking, retrying, clearing."""
import json
import time

import attachments
import chat
import db


class Uploaded:
    def __init__(self, name, data=b"x", mime="text/plain"):
        self.name, self.type, self._data = name, mime, data

    def getvalue(self):
        return self._data


def _wait(condition, timeout=5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# ── history ──────────────────────────────────────────────────────────────────
def test_history_maps_roles_and_skips_failed(database, case):
    database.add_message(case, "user", "أ")
    database.add_message(case, "assistant", "ب")
    database.add_message(case, "assistant", "", status="failed")
    database.add_message(case, "assistant", "   ", status="ok")     # blank content
    assert chat.history(case) == [{"role": "user", "content": "أ"},
                                  {"role": "assistant", "content": "ب"}]


def test_history_is_capped(database, case):
    for i in range(chat.MAX_HISTORY + 5):
        database.add_message(case, "user", str(i))
    rows = chat.history(case)
    assert len(rows) == chat.MAX_HISTORY
    assert rows[-1]["content"] == str(chat.MAX_HISTORY + 4)


# ── build_payload ────────────────────────────────────────────────────────────
def test_build_payload_basics(database, case):
    payload = chat.build_payload(database.get_case(case), "ar", "ما آخر التطورات؟")
    assert payload["mode"] == "chat"
    assert payload["question"] == "ما آخر التطورات؟"
    assert payload["history"] == []
    assert payload["case_number"] == "ALP-2026-001"


def test_build_payload_drops_the_current_question_from_history(database, case):
    database.add_message(case, "user", "سؤال")
    payload = chat.build_payload(database.get_case(case), "ar", "سؤال")
    assert payload["history"] == []


def test_build_payload_keeps_older_turns(database, case):
    database.add_message(case, "user", "قديم")
    database.add_message(case, "assistant", "رد")
    database.add_message(case, "user", "جديد")
    payload = chat.build_payload(database.get_case(case), "ar", "جديد")
    assert [m["content"] for m in payload["history"]] == ["قديم", "رد"]


def test_build_payload_flattens_report_json(database, case):
    database.update_case(case, report_text=json.dumps({"ملخص": "نص"}, ensure_ascii=False))
    payload = chat.build_payload(database.get_case(case), "ar", "س")
    assert payload["report_text"].startswith("ملخص")


def test_build_payload_limits_report_length(database, case):
    database.update_case(case, report_text="x" * (chat.MAX_REPORT_CHARS + 500))
    payload = chat.build_payload(database.get_case(case), "ar", "س")
    assert len(payload["report_text"]) == chat.MAX_REPORT_CHARS


def test_build_payload_includes_message_attachments(database, case):
    msg_id = database.add_message(case, "user", "س")
    attachments.save(case, Uploaded("note.txt", b"the file body"), message_id=msg_id)
    payload = chat.build_payload(database.get_case(case), "ar", "س", msg_id)
    assert "the file body" in payload["question"]
    assert payload["attachment_errors"] == []


# ── ask / reply ──────────────────────────────────────────────────────────────
def test_ask_stores_question_and_starts_reply(database, case, monkeypatch):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (True, "الرد"))
    msg_id, reply_id, saved, errors = chat.ask(case, "سؤال", "ar")
    assert saved == 0 and errors == []
    assert database.get_message(msg_id)["role"] == "user"
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert database.get_message(reply_id)["content"] == "الرد"
    assert database.get_message(reply_id)["reply_to"] == msg_id


def test_ask_marks_reply_failed(monkeypatch, database, case):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (False, "تعذّر"))
    _, reply_id, _, _ = chat.ask(case, "سؤال", "ar")
    assert _wait(lambda: database.get_message(reply_id)["status"] == "failed")
    assert database.get_message(reply_id)["error"] == "تعذّر"


def test_ask_saves_attachments_and_reports_failures(monkeypatch, database, case):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (True, "ok"))
    _, reply_id, saved, errors = chat.ask(
        case, "سؤال", "ar", uploaded=[Uploaded("a.txt", b"ok"), Uploaded("empty.txt", b"")])
    assert saved == 1 and len(errors) == 1
    assert "empty.txt" in errors[0]
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")


def test_reply_reads_the_question_it_answers(monkeypatch, database, case):
    captured = {}

    def fake_send(payload, lang):
        captured.update(payload)
        return True, "رد"

    monkeypatch.setattr(chat, "send_to_n8n", fake_send)
    msg_id = database.add_message(case, "user", "السؤال الأصلي")
    attachments.save(case, Uploaded("ev.txt", b"evidence text"), message_id=msg_id)
    reply_id = database.add_message(case, "assistant", "", status="pending", reply_to=msg_id)
    chat._run_reply(case, reply_id, "ar")
    assert captured["question"].startswith("السؤال الأصلي")
    assert "evidence text" in captured["question"]


def test_run_reply_gives_up_when_the_case_is_gone(database, case, monkeypatch):
    monkeypatch.setattr(chat, "send_to_n8n", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    reply_id = database.add_message(case, "assistant", "", status="pending")
    database.delete_case(case)
    chat._run_reply(case, reply_id, "ar")   # must return quietly


def test_retry_reopens_the_reply(monkeypatch, database, case):
    monkeypatch.setattr(chat, "send_to_n8n", lambda *a: (True, "محاولة ثانية"))
    reply_id = database.add_message(case, "assistant", "قديم", status="failed")
    chat.retry(case, reply_id, "ar")
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert database.get_message(reply_id)["content"] == "محاولة ثانية"


def test_reply_error_marks_the_reply_failed(monkeypatch, database, case):
    """An unexpected error while writing must not leave the reply 'pending' forever."""
    def boom(*a, **kw):
        raise RuntimeError("broken file")

    monkeypatch.setattr(chat, "build_payload", boom)
    reply_id = database.add_message(case, "assistant", "", status="pending")
    chat._run_reply(case, reply_id, "ar")
    reply = database.get_message(reply_id)
    assert reply["status"] == "failed"
    assert "broken file" in reply["error"]


# ── update report from a reply ───────────────────────────────────────────────
def test_prose_reply_joins_a_structured_report(database, case):
    report = {"الملخص": "سرقة", "الأدلة": ["كاميرا"], "مستوى الخطورة": "مرتفع"}
    database.update_case(case, report_text=json.dumps(report, ensure_ascii=False),
                         status="analyzed", severity="high")
    reply = database.add_message(case, "assistant", "الشاهد غيّر أقواله.", status="ok")
    chat.update_report(case, reply, "ar")
    saved = database.get_case(case)
    merged = json.loads(saved["report_text"])
    # Evidence and severity survive; the reply is one more section.
    assert merged["الأدلة"] == ["كاميرا"]
    assert merged["تحديث من المحادثة"] == "الشاهد غيّر أقواله."
    assert saved["severity"] == "high"
    assert len(database.list_report_versions(case)) == 1


def test_structured_reply_replaces_the_report(database, case):
    database.update_case(case, report_text='{"الملخص": "قديم"}', status="analyzed", severity="low")
    new = json.dumps({"الملخص": "جديد", "severity": "high"})
    reply = database.add_message(case, "assistant", new, status="ok")
    chat.update_report(case, reply, "ar")
    saved = database.get_case(case)
    assert json.loads(saved["report_text"])["الملخص"] == "جديد"
    assert saved["severity"] == "high"


def test_prose_reply_over_prose_report_keeps_the_severity(database, case):
    database.update_case(case, report_text="تقرير نصي", status="analyzed", severity="medium")
    reply = database.add_message(case, "assistant", "رد نصي", status="ok")
    chat.update_report(case, reply, "ar")
    saved = database.get_case(case)
    assert saved["report_text"] == "رد نصي"
    assert saved["severity"] == "medium"


def test_reply_with_message_attachments_updates_case_report(monkeypatch, database, case):
    previous = json.dumps({"ملخص القضية": "النتيجة الأولى", "الأدلة": [], "مستوى الخطورة": "منخفض"},
                          ensure_ascii=False)
    database.update_case(case, report_text=previous, status="analyzed", severity="low")
    monkeypatch.setattr(chat, "send_to_n8n", lambda *_args: (True, "المرفق يثبت اختلاف الكمية بين الفاتورة ومحضر الاستلام."))

    message_id, reply_id, saved, errors = chat.ask(
        case, "حلل المرفق وأضف نتيجته للتقرير.", "ar",
        uploaded=[Uploaded("new-evidence.txt", b"invoice quantity: 12, received quantity: 8")],
    )

    assert saved == 1 and errors == []
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert _wait(lambda: "تحديث من المحادثة" in database.get_case(case)["report_text"])
    report = json.loads(database.get_case(case)["report_text"])
    assert report["الأدلة"] == []
    assert report["تحديث من المحادثة"] == "المرفق يثبت اختلاف الكمية بين الفاتورة ومحضر الاستلام."
    assert database.list_report_versions(case)[0]["report_text"] == previous
    assert database.get_message(message_id)["role"] == "user"


# ── clear ────────────────────────────────────────────────────────────────────
def test_clear_removes_messages_and_their_files_but_keeps_case_files(database, case):
    msg_id = database.add_message(case, "user", "س")
    attachments.save(case, Uploaded("msg.txt", b"m"), message_id=msg_id)
    attachments.save(case, Uploaded("case.txt", b"c"))
    chat.clear(case)
    assert database.list_messages(case) == []
    assert [r["file_name"] for r in database.list_attachments(case)] == ["case.txt"]
