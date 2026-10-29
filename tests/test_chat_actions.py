"""Changes to the register proposed in the conversation: parsing, validation, confirmation."""
import json

import pytest
from fastapi.testclient import TestClient

import analysis
import chat
import chat_actions
import db
from api.main import app

REPORT = "بلاغ جديد: سرقة سيارة من موقف المستشفى الوطني صباح الأحد."


def _reply(database, action):
    """A reply in the conversation carrying a proposed action."""
    question = database.add_message(chat.GLOBAL_CHAT, "user", "طلب")
    reply = database.add_message(chat.GLOBAL_CHAT, "assistant", "سيتم التغيير بعد تأكيدك.",
                                 reply_to=question)
    database.update_message(reply, action=json.dumps(action, ensure_ascii=False))
    return reply


@pytest.fixture(autouse=True)
def no_side_jobs(monkeypatch):
    """No place lookups or analyses start for real; record what would have started."""
    started = []
    monkeypatch.setattr(chat_actions, "_locate_later", lambda case_id, lang: started.append(("locate", case_id)))
    monkeypatch.setattr(analysis, "start_analysis", lambda case_id, lang: started.append(("analyze", case_id)))
    return started


# ── reading the block ────────────────────────────────────────────────────────
def test_split_reply_removes_the_block():
    text = 'سأنشئ القضية بعد تأكيدك.\n<alpha-action>{"action": "analyze_case", "case": "ALP-2026-001"}</alpha-action>'
    content, data = chat_actions.split_reply(text)
    assert content == "سأنشئ القضية بعد تأكيدك."
    assert data == {"action": "analyze_case", "case": "ALP-2026-001"}


def test_split_reply_accepts_a_fenced_block_inside_the_tag():
    text = 'ok\n<alpha-action>\n```json\n{"action": "analyze_case", "case": "#3"}\n```\n</alpha-action>'
    assert chat_actions.split_reply(text) == ("ok", {"action": "analyze_case", "case": "#3"})


def test_split_reply_without_a_block():
    assert chat_actions.split_reply("  just an answer ") == ("just an answer", None)


def test_unreadable_block_becomes_an_invalid_proposal():
    content, data = chat_actions.split_reply("x <alpha-action>{not json</alpha-action>")
    assert content == "x" and data == {}
    action = chat_actions.propose(data, "en")
    assert action["status"] == "invalid"


# ── proposing ────────────────────────────────────────────────────────────────
def test_create_proposal_is_validated_and_normalized(database):
    action = chat_actions.propose({"action": "create_case", "fields": {
        "case_text": REPORT, "case_name": " سرقة سيارة ", "case_type": "Theft",
        "location": "", "date": "2026-10-25", "severity": "مرتفعة"}}, "ar")
    assert action["status"] == "pending"
    assert action["fields"] == {"case_name": "سرقة سيارة", "case_type": "سرقة", "date": "2026-10-25",
                                "case_text": REPORT, "severity": "high"}
    assert all(change["before"] is None for change in action["changes"])


@pytest.mark.parametrize("fields, message", [
    ({}, "description of what happened"),
    ({"case_text": "short"}, "too short"),
    ({"case_text": REPORT, "case_type": "Smuggling"}, "Unknown type"),
    ({"case_text": REPORT, "date": "25/10/2026"}, "YYYY-MM-DD"),
    ({"case_text": REPORT, "date": "2026-02-30"}, "YYYY-MM-DD"),
    ({"case_text": REPORT, "severity": "extreme"}, "low, medium, or high"),
    ({"case_text": REPORT, "status": "analyzed"}, "can't be set directly"),
    ({"case_text": REPORT, "report_text": "x"}, "report_text"),
    ({"case_text": REPORT, "case_name": ["a"]}, "invalid"),
    ({"case_text": REPORT, "case_name": "x" * 201}, "too long"),
])
def test_create_proposal_rejects_bad_input(database, fields, message):
    action = chat_actions.propose({"action": "create_case", "fields": fields}, "en")
    assert action["status"] == "invalid"
    assert message in action["error"]


def test_create_proposal_rejects_a_taken_case_number(database, case):
    action = chat_actions.propose({"action": "create_case", "fields": {
        "case_text": REPORT, "case_number": "ALP-2026-001"}}, "en")
    assert action["status"] == "invalid" and "already used" in action["error"]


def test_update_proposal_finds_the_case_by_number_and_records_before_values(database, case):
    action = chat_actions.propose({"action": "update_case", "case": "alp-2026-001",
                                   "fields": {"severity": "high", "case_name": "قضية تجريبية"},
                                   "append_text": "شاهد جديد رأى المشتبه به."}, "ar")
    assert action["status"] == "pending"
    assert (action["case_id"], action["case_number"]) == (case, "ALP-2026-001")
    # The unchanged title is dropped; only real changes are proposed.
    assert action["fields"] == {"severity": "high"}
    assert action["changes"] == [{"field": "severity", "before": None, "after": "high"}]
    assert action["append_text"] == "شاهد جديد رأى المشتبه به."


def test_update_proposal_by_id(database, case):
    action = chat_actions.propose({"action": "update_case", "case": f"#{case}",
                                   "fields": {"location": "حلب"}}, "en")
    assert action["status"] == "pending" and action["case_id"] == case


@pytest.mark.parametrize("data, message", [
    ({"case": "ALP-1999-999", "fields": {"severity": "low"}}, "not found"),
    ({"case": "ALP-2026-001", "fields": {"case_name": "قضية تجريبية"}}, "Nothing would change"),
    ({"case": "ALP-2026-001", "fields": {"case_text": REPORT}, "append_text": "more"}, "same request"),
    ({"case": "ALP-2026-001", "fields": {"case_number": ""}}, "can't be empty"),
])
def test_update_proposal_rejects_bad_input(database, case, data, message):
    action = chat_actions.propose({"action": "update_case", **data}, "en")
    assert action["status"] == "invalid" and message in action["error"]


def test_analyze_proposal_refuses_a_case_already_analyzing(database, case):
    database.update_case(case, status="analyzing")
    action = chat_actions.propose({"action": "analyze_case", "case": "ALP-2026-001"}, "en")
    assert action["status"] == "invalid" and "already being analyzed" in action["error"]


def test_unknown_action_is_invalid(database):
    action = chat_actions.propose({"action": "delete_case", "case": "ALP-2026-001"}, "en")
    assert (action["type"], action["status"]) == ("unknown", "invalid")


# ── confirming ───────────────────────────────────────────────────────────────
def test_confirm_create_saves_a_numbered_draft(database, no_side_jobs):
    proposal = chat_actions.propose({"action": "create_case", "fields": {
        "case_text": REPORT, "case_name": "سرقة سيارة", "case_type": "سرقة", "location": "دمشق"}}, "ar")
    reply = _reply(database, proposal)
    action = chat_actions.confirm(reply, "ar")
    assert action["status"] == "confirmed"
    created = database.get_case(action["case_id"])
    assert created["case_text"] == REPORT
    assert (created["case_name"], created["case_type"], created["location"]) == ("سرقة سيارة", "سرقة", "دمشق")
    assert created["status"] == "draft"
    assert created["case_number"] == action["case_number"]
    assert created["case_number"].startswith("ALP-")
    assert no_side_jobs == [("locate", created["id"])]
    # The outcome is stored on the reply, so the page and the model both see it.
    assert chat_actions.load(database.get_message(reply))["status"] == "confirmed"


def test_confirm_update_changes_fields_and_appends_to_the_report(database, case, no_side_jobs):
    database.update_case(case, latitude=33.5, longitude=36.3)
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001",
        "fields": {"location": "حمص", "severity": "medium"}, "append_text": "معلومة جديدة."}, "ar"))
    action = chat_actions.confirm(reply, "ar")
    assert action["status"] == "confirmed"
    row = database.get_case(case)
    assert (row["location"], row["severity"]) == ("حمص", "medium")
    assert row["case_text"].endswith("\n\nمعلومة جديدة.")
    # A new location drops the old pin and looks the new one up, as the case form does.
    assert (row["latitude"], row["longitude"]) == (None, None)
    assert no_side_jobs == [("locate", case)]


def test_confirm_update_refuses_when_the_case_changed_meanwhile(database, case):
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001", "fields": {"case_name": "اسم جديد"}}, "en"))
    database.update_case(case, case_name="اسم عدّله شخص آخر")
    action = chat_actions.confirm(reply, "en")
    assert action["status"] == "failed" and "changed since" in action["error"]
    assert database.get_case(case)["case_name"] == "اسم عدّله شخص آخر"


def test_confirm_update_refuses_a_deleted_case(database, case):
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001", "fields": {"severity": "low"}}, "en"))
    database.delete_case(case)
    action = chat_actions.confirm(reply, "en")
    assert action["status"] == "failed" and "no longer exists" in action["error"]


def test_confirm_rechecks_a_case_number_taken_meanwhile(database, case):
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {
        "case_text": REPORT, "case_number": "ALP-2026-050"}}, "en"))
    database.update_case(case, case_number="ALP-2026-050")
    action = chat_actions.confirm(reply, "en")
    assert action["status"] == "failed" and "already used" in action["error"]
    assert len(database.list_cases()) == 1


def test_confirm_analyze_starts_the_analysis(database, case, no_side_jobs):
    reply = _reply(database, chat_actions.propose({"action": "analyze_case", "case": "ALP-2026-001"}, "en"))
    assert chat_actions.confirm(reply, "en")["status"] == "confirmed"
    assert no_side_jobs == [("analyze", case)]


def test_an_action_is_applied_once(database):
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {"case_text": REPORT}}, "en"))
    assert chat_actions.confirm(reply, "en")["status"] == "confirmed"
    assert chat_actions.confirm(reply, "en") is None
    assert chat_actions.cancel(reply) is False
    assert len(database.list_cases()) == 1


def test_cancel_changes_nothing(database, case):
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001", "fields": {"severity": "low"}}, "en"))
    assert chat_actions.cancel(reply) is True
    assert chat_actions.confirm(reply, "en") is None
    assert database.get_case(case)["severity"] is None
    assert chat_actions.load(database.get_message(reply))["status"] == "cancelled"


def test_invalid_proposals_cannot_be_confirmed(database):
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {}}, "en"))
    assert chat_actions.confirm(reply, "en") is None
    assert database.list_cases() == []


def test_unexpected_error_leaves_the_action_failed(database, monkeypatch):
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {"case_text": REPORT}}, "en"))
    monkeypatch.setattr(db, "create_draft", lambda text: (_ for _ in ()).throw(RuntimeError("disk full")))
    action = chat_actions.confirm(reply, "en")
    assert action["status"] == "failed" and "disk full" in action["error"]


def test_restart_fails_actions_left_applying(database):
    reply = _reply(database, {"type": "create_case", "status": "applying", "fields": {}, "changes": []})
    database.fail_interrupted_actions("restarted")
    action = chat_actions.load(database.get_message(reply))
    assert (action["status"], action["error"]) == ("failed", "restarted")


# ── the conversation ─────────────────────────────────────────────────────────
def test_reply_with_a_block_stores_the_action(database, case, monkeypatch):
    block = '<alpha-action>{"action": "update_case", "case": "ALP-2026-001", "fields": {"severity": "high"}}</alpha-action>'
    monkeypatch.setattr(chat, "send_to_n8n", lambda payload, lang: (True, f"سأرفع الخطورة بعد تأكيدك.\n{block}"))
    question = database.add_message(chat.GLOBAL_CHAT, "user", "ارفع خطورة ALP-2026-001")
    reply = database.add_message(chat.GLOBAL_CHAT, "assistant", "", status="pending", reply_to=question)
    chat._write_reply(reply, "ar")
    row = database.get_message(reply)
    assert row["content"] == "سأرفع الخطورة بعد تأكيدك."
    assert chat_actions.load(row)["status"] == "pending"
    # Nothing changes until it is confirmed.
    assert database.get_case(case)["severity"] is None
    listed = chat.messages()[-1]
    assert listed["action"]["changes"] == [{"field": "severity", "before": None, "after": "high"}]


def test_retry_drops_the_previous_proposal(database, monkeypatch):
    monkeypatch.setattr(chat.threading, "Thread", lambda **kw: type("T", (), {"start": lambda self: None})())
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {"case_text": REPORT}}, "en"))
    database.update_message(reply, status="failed")
    chat.retry(reply, "en")
    assert database.get_message(reply)["action"] is None


def test_history_tells_the_model_what_became_of_an_action(database, case):
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001", "fields": {"severity": "low"}}, "en"))
    chat_actions.cancel(reply)
    last = chat.history()[-1]
    assert last["role"] == "assistant"
    assert "[Action update_case ALP-2026-001: cancelled]" in last["content"]


def test_questions_naming_a_case_get_its_full_details(database, case):
    other = database.create_draft("بلاغ احتيال مالي عبر تحويلات مصرفية مشبوهة متكررة.")
    database.update_case(other, case_number="ALP-2026-002", case_name="احتيال")
    payload = chat.build_payload("en", "What is new in alp-2026-002 and #999?", focus_case_id=case)
    assert "ALP-2026-002" in payload["referenced_cases"]
    assert "تحويلات مصرفية" in payload["referenced_cases"]
    # The open case is already sent in full, so it is not repeated.
    assert chat.build_payload("en", "and ALP-2026-001?", focus_case_id=case)["referenced_cases"] == ""


# ── API ──────────────────────────────────────────────────────────────────────
def test_confirm_endpoint_creates_the_case_and_lists_it(database):
    reply = _reply(database, chat_actions.propose({"action": "create_case", "fields": {
        "case_text": REPORT, "case_name": "سرقة سيارة"}}, "en"))
    with TestClient(app) as client:
        response = client.post(f"/api/messages/{reply}/action/confirm?lang=en")
        again = client.post(f"/api/messages/{reply}/action/confirm?lang=en")
        cases = client.get("/api/cases").json()["cases"]
        messages = client.get("/api/chat/messages").json()
    assert response.status_code == 200 and response.json()["status"] == "confirmed"
    assert again.status_code == 409 and again.json()["error"]["code"] == "action_not_pending"
    assert [c["case_name"] for c in cases] == ["سرقة سيارة"]
    assert messages[-1]["action"]["case_id"] == cases[0]["id"]


def test_cancel_endpoint(database, case):
    reply = _reply(database, chat_actions.propose({
        "action": "update_case", "case": "ALP-2026-001", "fields": {"severity": "low"}}, "en"))
    with TestClient(app) as client:
        response = client.post(f"/api/messages/{reply}/action/cancel")
    assert response.status_code == 200 and response.json()["status"] == "cancelled"
    assert database.get_case(case)["severity"] is None


def test_action_endpoints_need_a_message_with_an_action(database):
    plain = database.add_message(chat.GLOBAL_CHAT, "assistant", "just text")
    with TestClient(app) as client:
        missing = client.post("/api/messages/999/action/confirm")
        none = client.post(f"/api/messages/{plain}/action/cancel")
    assert missing.status_code == 404
    assert none.status_code == 404 and none.json()["error"]["code"] == "action_not_found"
