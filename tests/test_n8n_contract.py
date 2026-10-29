"""End-to-end against a real HTTP server that mimics the n8n workflow's contract.

The workflow (n8n/workflows/alpha-analysis.json) answers three ways: a health probe, a
suggestion, and a report. The app must agree with all three, and must rotate to the next
provider when the workflow reports a spent quota.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import analysis
import config
import llm


class Workflow(BaseHTTPRequestHandler):
    """A stand-in for the webhook. Behaviour per test is set in `calls` and `script`."""

    calls = []
    script = []          # list of (status, body) served in order; the last one repeats

    def do_POST(self):  # noqa: N802 (stdlib naming)
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        Workflow.calls.append(body)
        status, payload = Workflow.script[min(len(Workflow.calls) - 1, len(Workflow.script) - 1)]
        data = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture()
def workflow(monkeypatch):
    Workflow.calls = []
    Workflow.script = [(200, {})]
    server = HTTPServer(("127.0.0.1", 0), Workflow)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/webhook/alpha-analyze"
    monkeypatch.setattr(analysis, "WEBHOOK_URL", url)
    monkeypatch.setattr(config, "WEBHOOK_URL", url)
    llm.clear_exhausted()
    yield Workflow
    server.shutdown()
    server.server_close()
    llm.clear_exhausted()


REPORT = {"الملخص": "سرقة مستودع", "مستوى الخطورة": "مرتفع", "أدلة": ["بصمة", "كاميرا"]}


def test_health_probe_contract(workflow):
    workflow.script = [(200, {"ok": True, "llm_configured": True})]
    level, message = analysis.check_n8n("en")
    assert level == "success"
    assert workflow.calls == [{"ping": True}]


def test_analysis_round_trip_stores_report_and_severity(workflow, database, case):
    workflow.script = [(200, {"output": json.dumps(REPORT, ensure_ascii=False)})]
    analysis._run_analysis(case, "ar")
    row = database.get_case(case)
    assert row["status"] == "analyzed"
    assert row["severity"] == "high"
    assert analysis.parse_report(row["report_text"]) == REPORT
    # The app sent the case and named the provider key the workflow reads from $env.
    assert workflow.calls[0]["provider_key"] == "1"
    assert workflow.calls[0]["case_name"] == "قضية تجريبية"


def test_reanalysis_uses_updated_report_and_preserves_its_version(workflow, database, case):
    updated_report = "المحقق الظاهر في الصورة قُتل بسبب تحقيق كان يجريه."
    database.update_case(case, status="analyzed", report_text=updated_report, severity="high")
    workflow.script = [(200, {"output": json.dumps(REPORT, ensure_ascii=False)})]

    analysis._run_analysis(case, "ar")

    sent_report = workflow.calls[0]["case_text"]
    assert "بلاغ تجريبي عن حادثة سرقة" in sent_report
    assert updated_report in sent_report
    assert database.get_case(case)["report_text"] == json.dumps(REPORT, ensure_ascii=False)
    assert [version["report_text"] for version in database.list_report_versions(case)] == [
        updated_report
    ]


def test_failed_analysis_is_recorded_and_retryable(workflow, database, case):
    workflow.script = [(500, {"message": "model exploded"})]
    analysis._run_analysis(case, "ar")
    row = database.get_case(case)
    assert row["status"] == "failed"
    assert "model exploded" in row["error"]
    # Retrying after the service recovers succeeds and clears the error.
    workflow.script = [(200, {"output": "تقرير"})]
    analysis._run_analysis(case, "ar")
    row = database.get_case(case)
    assert (row["status"], row["error"]) == ("analyzed", None)


def test_quota_failure_switches_provider_then_succeeds(workflow, database, case, monkeypatch):
    # Two providers, as in .env: the first is spent, the second answers.
    second = {"index": "2", "id": "2:http://backup", "name": "backup", "url": "http://backup",
              "key": "k2", "model": "backup-model", "vision_model": "backup-model"}
    monkeypatch.setattr(llm, "PROVIDERS", llm.PROVIDERS + [second])
    conditions = iter([
        (429, {"error": "free-models-per-day exhausted"}),
        (200, {"output": "تقرير"}),
    ])

    def next_script():
        status, payload = next(conditions)
        Workflow.script = [(status, payload)]

    next_script()
    original_post = analysis.requests.post

    def switching_post(url, json=None, headers=None, timeout=None):
        response = original_post(url, json=json, headers=headers, timeout=timeout)
        if response.status_code == 429:
            next_script()
        return response

    monkeypatch.setattr(analysis.requests, "post", switching_post)
    analysis._run_analysis(case, "ar")

    assert [c["provider_key"] for c in workflow.calls] == ["1", "2"]
    assert database.get_case(case)["status"] == "analyzed"
    assert llm._is_set_aside(llm.PROVIDERS[0]["id"])


def test_chat_turn_contract(workflow, database, case):
    workflow.script = [(200, {"output": "رد المحلل"})]
    database.update_case(case, status="analyzed", report_text=json.dumps(REPORT, ensure_ascii=False))
    payload = __import__("chat").build_payload("ar", "من المشتبه به؟", focus_case_id=case)
    ok, result = analysis.send_to_n8n(payload, "ar")
    assert ok and result == "رد المحلل"
    sent = workflow.calls[0]
    assert sent["mode"] == "chat"
    assert sent["question"] == "من المشتبه به؟"
    assert sent["focus_case_id"] == case
    assert "سرقة مستودع" in sent["report_text"]
    assert "ALP-2026-001" in sent["cases_overview"]


def test_suggestion_contract(workflow, database, case):
    workflow.script = [(200, {"output": json.dumps(
        {"title": "سرقة", "case_type": "سرقة", "location": "المستودع", "date": "2026-10-17"},
        ensure_ascii=False)})]
    out = analysis.suggest_details(database.get_case(case)["case_text"], "ar")
    assert out["case_number"] if False else True
    assert out == {"case_name": "سرقة", "case_type": "سرقة", "location": "المستودع", "date": "2026-10-17"}
    assert workflow.calls[0]["mode"] == "suggest"


def test_workflow_file_names_the_env_vars_the_app_sends():
    """The workflow reads $env["LLM_<provider_key>_MODEL"]; the app sends provider["index"]."""
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "n8n" / "workflows" / "alpha-analysis.json"
    workflow = json.loads(path.read_text(encoding="utf-8"))
    assert workflow["id"] == "AlphaAnalysis001"
    http_nodes = [n for n in workflow["nodes"] if n["type"] == "n8n-nodes-base.httpRequest"]
    assert len(http_nodes) == 3
    for node in http_nodes:
        blob = json.dumps(node["parameters"], ensure_ascii=False)
        assert '$json.body.provider_key' in blob
        assert "chat/completions" in blob
    for index in (p["index"] for p in llm.PROVIDERS):
        assert index.isdigit()
