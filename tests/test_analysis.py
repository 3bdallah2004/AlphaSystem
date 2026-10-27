"""Report parsing, output extraction, severity detection, and the n8n client."""
import json
import threading

import pytest
import requests

import analysis
import llm
from i18n import t


# ── parse_report ─────────────────────────────────────────────────────────────
def test_parse_plain_json():
    assert analysis.parse_report('{"a": 1}') == {"a": 1}


def test_parse_fenced_json():
    assert analysis.parse_report('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_fenced_without_language():
    assert analysis.parse_report('```\n{"a": 1}\n```') == {"a": 1}


def test_parse_rejects_non_object():
    assert analysis.parse_report("[1, 2]") is None
    assert analysis.parse_report('"text"') is None


def test_parse_rejects_garbage_and_empty():
    assert analysis.parse_report("not json at all") is None
    assert analysis.parse_report("") is None
    assert analysis.parse_report(None) is None


def test_parse_rejects_truncated_json():
    assert analysis.parse_report('{"a": [1, 2') is None


def test_parse_handles_arabic():
    assert analysis.parse_report('{"الملخص": "سرقة"}')


# ── extract_severity ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("payload,expected", [
    ({"مستوى الخطورة": "مرتفع"}, "high"),
    ({"الخطورة": "عالية"}, "high"),
    ({"severity": "CRITICAL"}, "high"),
    ({"Severity": "Medium"}, "medium"),
    ({"خطورة القضية": "متوسطة"}, "medium"),
    ({"severity": "low"}, "low"),
])
def test_extract_severity(payload, expected):
    assert analysis.extract_severity(json.dumps(payload, ensure_ascii=False)) == expected


@pytest.mark.parametrize("value,expected", [
    ("not high", None),
    ("Not high, but medium", "medium"),
    ("non-critical; low", "low"),
    ("غير مرتفعة", None),
    ("ليست عالية بل متوسطة", "medium"),
    ("الخطورة العالية", "high"),
    ("Medium to high", "medium"),
    ("High (the risk is not low)", "high"),
    ("الأدلة فعالة لكن الخطورة منخفضة", "low"),     # "فعالة" is not "عالية"
    ("below average", None),                           # "below" is not "low"
])
def test_severity_level_reads_negations_and_whole_words(value, expected):
    assert analysis.severity_level(value) == expected


def test_extract_severity_unknown_or_missing():
    assert analysis.extract_severity('{"الملخص": "لا شيء"}') is None
    assert analysis.extract_severity("نص عادي") is None
    assert analysis.extract_severity(None) is None


# ── find_key / report_as_text ────────────────────────────────────────────────
def test_find_key_matches_case_insensitively():
    report = {"Items of Evidence": ["x"]}
    assert analysis.find_key(report, "أدلة", "evidence") == "Items of Evidence"
    assert analysis.find_key(report, "parties") is None


def test_report_as_text_flattens_lists_and_dicts():
    text = analysis.report_as_text(json.dumps(
        {"ملخص": "قصير", "أدلة": ["أ", "ب"], "أطراف": {"متهم": "س"}}, ensure_ascii=False))
    assert "ملخص\nقصير" in text
    assert "- أ" in text and "- ب" in text
    assert "- متهم: س" in text


def test_report_as_text_passthrough_for_plain_text():
    assert analysis.report_as_text("تقرير حر") == "تقرير حر"
    assert analysis.report_as_text(None) == ""


# ── extract_output ───────────────────────────────────────────────────────────
class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload, self.text, self.status_code = payload, text, status_code

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


def test_extract_output_text_response():
    assert analysis.extract_output(FakeResponse(text="  تقرير  "), "ar") == "تقرير"


def test_extract_output_arabic_key():
    assert analysis.extract_output(FakeResponse({"المخرجات": "تقرير"}), "ar") == "تقرير"


def test_extract_output_list_of_items():
    out = analysis.extract_output(FakeResponse([{"output": "أ"}, {"output": "ب"}]), "ar")
    assert out == "أ\n\nب"


def test_extract_output_unknown_keys_fall_back_to_json_dump():
    out = analysis.extract_output(FakeResponse({"foo": "bar"}), "ar")
    assert json.loads(out) == {"foo": "bar"}


def test_extract_output_empty_json_gives_localized_message():
    out = analysis.extract_output(FakeResponse({}), "en")
    assert "No analysis" in out


def test_extract_output_non_json_body_falls_back_to_text():
    assert analysis.extract_output(FakeResponse(None, text="oops"), "ar") == "oops"


def test_extract_output_empty_body_is_localized():
    from i18n import t

    assert analysis.extract_output(FakeResponse(None, text=""), "ar") == t("ar", "empty_response")


# ── case_payload ─────────────────────────────────────────────────────────────
def test_case_payload_translates_type(database, case):
    database.update_case(case, case_type="سرقة", case_name="عنوان")
    payload = analysis.case_payload(database.get_case(case), "en")
    assert payload["case_type"] == "Theft"
    assert payload["case_name"] == "عنوان"
    assert payload["language"] == "en"


def test_case_payload_marks_previous_analysis_as_context(database, case):
    updated_report = "التقرير المحدّث يتضمن معلومة جديدة عن القضية."
    database.update_case(case, report_text=updated_report)

    payload = analysis.case_payload(database.get_case(case), "ar")

    assert "نص البلاغ الأصلي المحدّث (المصدر المعتمد):" in payload["case_text"]
    assert "بلاغ تجريبي عن حادثة سرقة" in payload["case_text"]
    assert "التحليل السابق (للسياق فقط؛ أعد تقييمه" in payload["case_text"]
    assert updated_report in payload["case_text"]
    assert "أنشئ تقريراً جديداً" in payload["case_text"]


def test_reanalysis_uses_updated_report_and_preserves_previous_version(database, case, monkeypatch):
    previous = '{"ملخص القضية":"النتيجة السابقة","مستوى الخطورة":"منخفض"}'
    updated = '{"ملخص القضية":"النتيجة الجديدة","مستوى الخطورة":"مرتفع"}'
    source = "بلاغ محدّث يذكر أن الشحنة لم تصل إلى المستودع."
    database.update_case(case, case_text=source, report_text=previous, status="analyzed",
                         latitude=31.9, longitude=35.2)
    captured = {}

    monkeypatch.setattr(analysis, "attachments_for_prompt", lambda *_args: ("", [], 0))
    monkeypatch.setattr(
        analysis, "send_to_n8n",
        lambda payload, lang: (captured.update(payload=payload, language=lang) or True, updated),
    )

    analysis._analyze(case, "ar")

    saved = database.get_case(case)
    assert source in captured["payload"]["case_text"]
    assert previous in captured["payload"]["case_text"]
    assert saved["report_text"] == updated
    assert saved["severity"] == "high"
    assert [version["report_text"] for version in database.list_report_versions(case)] == [previous]


def test_outdated_analysis_run_cannot_overwrite_a_newer_request(database, case, monkeypatch):
    previous = '{"ملخص القضية":"النسخة المحفوظة"}'
    database.update_case(case, case_text="بلاغ محدّث", report_text=previous, status="analyzing",
                         latitude=31.9, longitude=35.2)
    monkeypatch.setitem(analysis._analysis_generations, case, 1)
    monkeypatch.setattr(analysis, "attachments_for_prompt", lambda *_args: ("", [], 0))

    def supersede(payload, lang):
        analysis._analysis_generations[case] = 2
        return True, '{"ملخص القضية":"نتيجة قديمة"}'

    monkeypatch.setattr(analysis, "send_to_n8n", supersede)
    analysis._analyze(case, "ar", generation=1)

    assert database.get_case(case)["report_text"] == previous
    assert database.list_report_versions(case) == []


def test_case_payload_survives_null_columns(database, case):
    payload = analysis.case_payload(database.get_case(case), "ar")
    assert payload["incident_location"] == ""
    assert payload["incident_date"] == ""


# ── send_to_n8n ──────────────────────────────────────────────────────────────
def test_send_to_n8n_success(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return FakeResponse({"output": "تقرير"})

    monkeypatch.setattr(analysis.requests, "post", fake_post)
    ok, result = analysis.send_to_n8n({"case_text": "x"}, "ar")
    assert ok and result == "تقرير"
    assert seen["payload"]["provider_key"] == "1"          # tells the workflow which key to use


def test_send_to_n8n_logs_timing_without_payload(monkeypatch, caplog):
    monkeypatch.setattr(analysis.requests, "post", lambda *a, **kw: FakeResponse({"output": "private report"}))

    with caplog.at_level("INFO", logger="analysis"):
        assert analysis.send_to_n8n({"mode": "chat", "question": "private question"}, "ar") == (
            True, "private report"
        )

    assert "AI timing mode=chat provider=1 outcome=success elapsed_seconds=" in caplog.text
    assert "private question" not in caplog.text
    assert "private report" not in caplog.text


def test_send_to_n8n_connection_error_is_localized(monkeypatch):
    def fake_post(*a, **kw):
        raise requests.exceptions.ConnectionError("refused")

    monkeypatch.setattr(analysis.requests, "post", fake_post)
    ok, result = analysis.send_to_n8n({"case_text": "x"}, "ar")
    assert not ok
    assert "خدمة التحليل" in result


def test_send_to_n8n_timeout(monkeypatch):
    from i18n import t

    def fake_post(*a, **kw):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(analysis.requests, "post", fake_post)
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok and result == t("ar", "err_timeout")


def test_send_to_n8n_404_means_workflow_inactive(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: FakeResponse(None, "not registered", 404))
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok
    assert "سير عمل التحليل" in result


def test_send_to_n8n_server_error_is_reported(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: FakeResponse({"message": "boom"}, "", 500))
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok
    assert "HTTP 500" in result and "boom" in result


def test_send_to_n8n_sets_provider_aside_on_quota(monkeypatch):
    llm.clear_exhausted()
    responses = iter([FakeResponse({"error": "rate limit exceeded"}, "", 429)])

    monkeypatch.setattr(analysis.requests, "post", lambda *a, **kw: next(responses))
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok
    assert llm._is_set_aside(llm.PROVIDERS[0]["id"])
    llm.clear_exhausted()


def test_send_to_n8n_without_providers_says_so(monkeypatch):
    """No provider configured is a setup problem, not a quota error (it used to say HTTP 429)."""
    monkeypatch.setattr(analysis.llm, "PROVIDERS", [])
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: (_ for _ in ()).throw(AssertionError("no request expected")))
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok
    assert result == t("ar", "err_no_provider")
    assert "429" not in result


def test_send_to_n8n_sends_the_webhook_token(monkeypatch):
    seen = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen["headers"] = headers
        return FakeResponse({"output": "ok"})

    monkeypatch.setattr(analysis, "WEBHOOK_TOKEN", "s3cret")
    monkeypatch.setattr(analysis.requests, "post", fake_post)
    assert analysis.send_to_n8n({}, "ar") == (True, "ok")
    assert seen["headers"] == {"X-Alpha-Token": "s3cret"}


def test_send_to_n8n_401_explains_the_token(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post", lambda *a, **kw: FakeResponse({"error": "x"}, "", 401))
    ok, result = analysis.send_to_n8n({}, "ar")
    assert not ok and result == t("ar", "err_unauthorized")


def test_analysis_thread_error_marks_the_case_failed(database, case, monkeypatch):
    """An unexpected error in the background must not leave the case 'analyzing' forever."""
    def boom(*a, **kw):
        raise RuntimeError("corrupt attachment")

    monkeypatch.setattr(analysis, "attachments_for_prompt", boom)
    database.update_case(case, status="analyzing", latitude=31.9, longitude=35.2)
    analysis._run_analysis(case, "ar")
    row = database.get_case(case)
    assert row["status"] == "failed"
    assert "corrupt attachment" in row["error"]


def test_check_n8n_unauthorized(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post", lambda *a, **kw: FakeResponse(None, "x", 401))
    level, msg = analysis.check_n8n("ar")
    assert level == "error" and msg == t("ar", "chk_unauthorized")


# ── check_n8n ────────────────────────────────────────────────────────────────
def test_check_n8n_unreachable(monkeypatch):
    def boom(*a, **kw):
        raise requests.exceptions.ConnectionError()

    monkeypatch.setattr(analysis.requests, "post", boom)
    level, _ = analysis.check_n8n("ar")
    assert level == "error"


def test_check_n8n_not_active(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post", lambda *a, **kw: FakeResponse(None, "x", 404))
    level, msg = analysis.check_n8n("ar")
    assert level == "error" and "سير عمل" in msg


def test_check_n8n_missing_key(monkeypatch):
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: FakeResponse({"ok": True, "llm_configured": False}))
    level, _ = analysis.check_n8n("ar")
    assert level == "warning"


def test_check_n8n_ready(monkeypatch):
    llm.clear_exhausted()
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: FakeResponse({"ok": True, "llm_configured": True}))
    level, msg = analysis.check_n8n("ar")
    assert level == "success"
    assert "test-model" in msg


def test_check_n8n_all_providers_spent(monkeypatch):
    llm.clear_exhausted()
    monkeypatch.setattr(analysis.requests, "post",
                        lambda *a, **kw: FakeResponse({"ok": True, "llm_configured": True}))
    llm.set_aside(1)
    level, _ = analysis.check_n8n("ar")
    assert level == "warning"
    llm.clear_exhausted()


# ── suggest_details ──────────────────────────────────────────────────────────
def test_suggest_details_keeps_valid_fields(monkeypatch):
    monkeypatch.setattr(analysis, "send_to_n8n", lambda *a, **kw: (True, json.dumps({
        "title": " عنوان ", "case_type": "سرقة", "location": "مكان", "date": "2026-10-01",
    }, ensure_ascii=False)))
    out = analysis.suggest_details("نص", "ar")
    assert out == {"case_name": "عنوان", "case_type": "سرقة", "location": "مكان", "date": "2026-10-01"}


def test_suggest_details_drops_invalid_type_and_date(monkeypatch):
    monkeypatch.setattr(analysis, "send_to_n8n", lambda *a, **kw: (True, json.dumps({
        "title": "عنوان", "case_type": "غير موجود", "date": "01/10/2026",
    }, ensure_ascii=False)))
    out = analysis.suggest_details("نص", "ar")
    assert out == {"case_name": "عنوان"}


def test_suggest_details_failure_returns_empty(monkeypatch):
    monkeypatch.setattr(analysis, "send_to_n8n", lambda *a, **kw: (False, "err"))
    assert analysis.suggest_details("نص", "ar") == {}


def test_analysis_overlaps_geocoding_with_attachment_preparation(monkeypatch):
    case = {
        "id": 1, "latitude": None, "longitude": None, "case_name": "Case",
        "case_text": "Original report", "case_number": "1", "case_type": "عام",
        "location": "Place", "date": "", "report_text": "",
    }
    geocode_started = threading.Event()
    finish_geocode = threading.Event()
    monkeypatch.setattr(analysis.db, "get_case", lambda case_id: case)

    def locate(case_id, lang):
        geocode_started.set()
        assert finish_geocode.wait(timeout=2)

    def attachments_for_prompt(case_id, lang):
        assert geocode_started.wait(timeout=2)
        finish_geocode.set()
        return "Attachment text", [], 0

    def send_to_n8n(payload, lang):
        assert "Attachment text" in payload["case_text"]
        return True, '{"severity": "low"}'

    monkeypatch.setattr(analysis, "locate", locate)
    monkeypatch.setattr(analysis, "attachments_for_prompt", attachments_for_prompt)
    monkeypatch.setattr(analysis, "send_to_n8n", send_to_n8n)
    monkeypatch.setattr(analysis.db, "save_analysis_report", lambda *args: None)
    try:
        analysis._analyze(1, "ar")
    finally:
        finish_geocode.set()
