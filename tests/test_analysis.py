"""Report parsing, output extraction, severity detection, and the n8n client."""
import json

import pytest
import requests

import analysis
import llm


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


def test_case_payload_includes_current_report_when_reanalyzing(database, case):
    updated_report = "التقرير المحدّث يتضمن معلومة جديدة عن القضية."
    database.update_case(case, report_text=updated_report)

    payload = analysis.case_payload(database.get_case(case), "ar")

    assert "نص البلاغ الأصلي:" in payload["case_text"]
    assert "بلاغ تجريبي عن حادثة سرقة" in payload["case_text"]
    assert updated_report in payload["case_text"]


def test_case_payload_survives_null_columns(database, case):
    payload = analysis.case_payload(database.get_case(case), "ar")
    assert payload["incident_location"] == ""
    assert payload["incident_date"] == ""


# ── send_to_n8n ──────────────────────────────────────────────────────────────
def test_send_to_n8n_success(monkeypatch):
    seen = {}

    def fake_post(url, json=None, timeout=None):
        seen.update(url=url, payload=json, timeout=timeout)
        return FakeResponse({"output": "تقرير"})

    monkeypatch.setattr(analysis.requests, "post", fake_post)
    ok, result = analysis.send_to_n8n({"case_text": "x"}, "ar")
    assert ok and result == "تقرير"
    assert seen["payload"]["provider_key"] == "1"          # tells the workflow which key to use


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
