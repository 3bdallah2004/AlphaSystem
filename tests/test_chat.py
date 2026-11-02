"""The global conversation: history, payload building, asking, retrying, clearing."""
import json
import time

import attachments
import chat


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


def _say(database, role, content, **kw):
    return database.add_message(chat.GLOBAL_CHAT, role, content, **kw)


# ── history ──────────────────────────────────────────────────────────────────
def test_history_maps_roles_and_skips_failed(database):
    _say(database, "user", "أ")
    _say(database, "assistant", "ب")
    _say(database, "assistant", "", status="failed")
    _say(database, "assistant", "   ", status="ok")     # blank content
    assert chat.history() == [{"role": "user", "content": "أ"},
                              {"role": "assistant", "content": "ب"}]


def test_history_is_capped(database):
    for i in range(chat.MAX_HISTORY + 5):
        _say(database, "user", str(i))
    rows = chat.history()
    assert len(rows) == chat.MAX_HISTORY
    assert rows[-1]["content"] == str(chat.MAX_HISTORY + 4)


def test_history_ignores_old_per_case_conversations(database, case):
    database.add_message(case, "user", "قديم")
    _say(database, "user", "جديد")
    assert chat.history() == [{"role": "user", "content": "جديد"}]


# ── cases overview ───────────────────────────────────────────────────────────
def test_overview_lists_every_case(database, case):
    other = database.create_draft("بلاغ احتيال مالي عبر الإنترنت.")
    database.update_case(other, case_name="احتيال", case_number="ALP-2026-002",
                         report_text=json.dumps({"ملخص": "تحويلات مشبوهة"}, ensure_ascii=False))
    overview = chat.cases_overview("ar")
    assert "ALP-2026-001" in overview and "ALP-2026-002" in overview
    assert "تحويلات مشبوهة" in overview          # the analysis, flattened
    assert "المستودع المركزي" in overview         # the report of a case not analyzed yet


def test_overview_without_cases(database):
    assert chat.cases_overview("en") == "No cases are registered yet."


def test_overview_shortens_long_reports(database, case):
    database.update_case(case, report_text="x" * (chat.MAX_SUMMARY_CHARS * 3))
    assert "x" * (chat.MAX_SUMMARY_CHARS + 1) not in chat.cases_overview("ar")


# ── build_payload ────────────────────────────────────────────────────────────
def test_build_payload_basics(database, case):
    payload = chat.build_payload("ar", "ما آخر التطورات؟")
    assert payload["mode"] == "chat"
    assert payload["question"] == "ما آخر التطورات؟"
    assert payload["history"] == []
    assert payload["focus_case_id"] is None
    assert payload["case_number"] == ""
    assert "ALP-2026-001" in payload["cases_overview"]


def test_build_payload_includes_the_open_case(database, case):
    payload = chat.build_payload("ar", "س", focus_case_id=case)
    assert payload["focus_case_id"] == case
    assert payload["case_number"] == "ALP-2026-001"
    assert "المستودع المركزي" in payload["case_text"]


def test_build_payload_ignores_a_deleted_open_case(database, case):
    database.delete_case(case)
    assert chat.build_payload("ar", "س", focus_case_id=case)["focus_case_id"] is None


def test_build_payload_drops_the_current_question_from_history(database):
    _say(database, "user", "سؤال")
    assert chat.build_payload("ar", "سؤال")["history"] == []


def test_build_payload_keeps_older_turns(database):
    _say(database, "user", "قديم")
    _say(database, "assistant", "رد")
    _say(database, "user", "جديد")
    payload = chat.build_payload("ar", "جديد")
    assert [m["content"] for m in payload["history"]] == ["قديم", "رد"]


def test_build_payload_flattens_report_json(database, case):
    database.update_case(case, report_text=json.dumps({"ملخص": "نص"}, ensure_ascii=False))
    payload = chat.build_payload("ar", "س", focus_case_id=case)
    assert payload["report_text"].startswith("ملخص")


def test_build_payload_limits_report_length(database, case):
    database.update_case(case, report_text="x" * (chat.MAX_REPORT_CHARS + 500))
    payload = chat.build_payload("ar", "س", focus_case_id=case)
    assert len(payload["report_text"]) == chat.MAX_REPORT_CHARS


def test_build_payload_includes_message_attachments(database):
    msg_id = _say(database, "user", "س")
    attachments.save(chat.GLOBAL_CHAT, Uploaded("note.txt", b"the file body"), message_id=msg_id)
    payload = chat.build_payload("ar", "س", msg_id)
    assert "the file body" in payload["question"]
    assert payload["attachment_errors"] == []


# ── ask / reply ──────────────────────────────────────────────────────────────
def test_ask_stores_question_and_starts_reply(database, monkeypatch):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (True, "الرد"))
    msg_id, reply_id, saved, errors = chat.ask("سؤال", "ar")
    assert saved == 0 and errors == []
    assert database.get_message(msg_id)["role"] == "user"
    assert database.get_message(msg_id)["case_id"] == chat.GLOBAL_CHAT
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert database.get_message(reply_id)["content"] == "الرد"
    assert database.get_message(reply_id)["reply_to"] == msg_id


def test_ask_sends_the_open_case(database, case, monkeypatch):
    captured = {}

    def fake_send(payload, lang):
        captured.update(payload)
        return True, "رد"

    monkeypatch.setattr(chat, "send_to_n8n", fake_send)
    _, reply_id, _, _ = chat.ask("ما خطورة هذه القضية؟", "ar", focus_case_id=case)
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert captured["focus_case_id"] == case
    assert captured["case_number"] == "ALP-2026-001"


def test_ask_marks_reply_failed(monkeypatch, database):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (False, "تعذّر"))
    _, reply_id, _, _ = chat.ask("سؤال", "ar")
    assert _wait(lambda: database.get_message(reply_id)["status"] == "failed")
    assert database.get_message(reply_id)["error"] == "تعذّر"


def test_ask_saves_attachments_and_reports_failures(monkeypatch, database):
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (True, "ok"))
    _, reply_id, saved, errors = chat.ask(
        "سؤال", "ar", uploaded=[Uploaded("a.txt", b"ok"), Uploaded("empty.txt", b"")])
    assert saved == 1 and len(errors) == 1
    assert "empty.txt" in errors[0]
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")


def test_reply_reads_the_question_it_answers(monkeypatch, database):
    captured = {}

    def fake_send(payload, lang):
        captured.update(payload)
        return True, "رد"

    monkeypatch.setattr(chat, "send_to_n8n", fake_send)
    msg_id = _say(database, "user", "السؤال الأصلي")
    attachments.save(chat.GLOBAL_CHAT, Uploaded("ev.txt", b"evidence text"), message_id=msg_id)
    reply_id = _say(database, "assistant", "", status="pending", reply_to=msg_id)
    chat._run_reply(reply_id, "ar")
    assert captured["question"].startswith("السؤال الأصلي")
    assert "evidence text" in captured["question"]


def test_run_reply_gives_up_when_the_reply_is_gone(database, monkeypatch):
    monkeypatch.setattr(chat, "send_to_n8n", lambda *a: (_ for _ in ()).throw(AssertionError("called")))
    reply_id = _say(database, "assistant", "", status="pending")
    chat.clear()
    chat._run_reply(reply_id, "ar")   # must return quietly


def test_retry_reopens_the_reply(monkeypatch, database):
    monkeypatch.setattr(chat, "send_to_n8n", lambda *a: (True, "محاولة ثانية"))
    reply_id = _say(database, "assistant", "قديم", status="failed")
    chat.retry(reply_id, "ar")
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert database.get_message(reply_id)["content"] == "محاولة ثانية"


def test_reply_error_marks_the_reply_failed(monkeypatch, database):
    """An unexpected error while writing must not leave the reply 'pending' forever."""
    def boom(*a, **kw):
        raise RuntimeError("broken file")

    monkeypatch.setattr(chat, "build_payload", boom)
    reply_id = _say(database, "assistant", "", status="pending")
    chat._run_reply(reply_id, "ar")
    reply = database.get_message(reply_id)
    assert reply["status"] == "failed"
    assert "broken file" in reply["error"]


def test_replies_never_change_case_reports(monkeypatch, database, case):
    database.update_case(case, report_text='{"الملخص": "أصلي"}', status="analyzed")
    monkeypatch.setattr(chat, "send_to_n8n", lambda *_args: (True, "رد"))
    _, reply_id, _, _ = chat.ask("حلل المرفق", "ar", uploaded=[Uploaded("e.txt", b"evidence")],
                                 focus_case_id=case)
    assert _wait(lambda: database.get_message(reply_id)["status"] == "ok")
    assert database.get_case(case)["report_text"] == '{"الملخص": "أصلي"}'


# ── listing / clear ──────────────────────────────────────────────────────────
def test_messages_include_their_files(database):
    msg_id = _say(database, "user", "س")
    attachments.save(chat.GLOBAL_CHAT, Uploaded("msg.txt", b"m"), message_id=msg_id)
    assert chat.messages()[0]["attachments"][0]["file_name"] == "msg.txt"


def test_clear_removes_messages_and_their_files_but_keeps_case_files(database, case):
    msg_id = _say(database, "user", "س")
    attachments.save(chat.GLOBAL_CHAT, Uploaded("msg.txt", b"m"), message_id=msg_id)
    attachments.save(case, Uploaded("case.txt", b"c"))
    chat.clear()
    assert chat.messages() == []
    assert database.list_attachments(chat.GLOBAL_CHAT) == []
    assert [r["file_name"] for r in database.list_attachments(case)] == ["case.txt"]
