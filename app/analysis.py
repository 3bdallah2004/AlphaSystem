"""Client for the n8n analysis workflow (n8n/workflows/alpha-analysis.json)."""
import json
import re
import threading

import requests

import config
import db
import extract
import geocode
import llm
import vision
from config import REQUEST_TIMEOUT, WEBHOOK_URL
from i18n import CASE_TYPES, case_type_label, t

OUTPUT_KEYS = ["output", "المخرجات", "report", "result", "response", "text", "message"]
CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.S)
SEVERITY_WORDS = {
    "high": ("مرتفع", "عال", "high", "critical"),
    "medium": ("متوسط", "medium", "moderate"),
    "low": ("منخفض", "low"),
}


def case_payload(case, language):
    case_text = case["case_text"] or ""
    current_report = (case.get("report_text") or "").strip()
    if current_report:
        if language == "en":
            case_text = (
                f"Original report:\n{case_text}\n\n"
                f"Latest saved report and analysis; treat it as the newest case information:\n"
                f"{current_report}"
            ).strip()
        else:
            case_text = (
                f"نص البلاغ الأصلي:\n{case_text}\n\n"
                f"أحدث تقرير وتحليل محفوظ؛ اعتمده بوصفه أحدث معلومات القضية:\n"
                f"{current_report}"
            ).strip()
    return {
        "case_name": case["case_name"] or "", "case_text": case_text,
        "case_number": case["case_number"] or "",
        "case_type": case_type_label(language, case["case_type"] or "عام"),
        "incident_location": case["location"] or "", "incident_date": case["date"] or "",
        "language": language,
    }


def parse_report(text):
    """The analysis as a dict when the model returned JSON (possibly in a ``` block), else None."""
    text = str(text or "").strip()
    fenced = CODE_FENCE_RE.match(text)
    candidate = fenced.group(1) if fenced else text
    if candidate[:1] != "{":
        return None
    try:
        parsed = json.loads(candidate)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def find_key(report, *needles):
    return next((k for k in report if any(n in k.lower() for n in needles)), None)


def extract_severity(report_text):
    report = parse_report(report_text)
    if not report:
        return None
    key = find_key(report, "خطورة", "severity")
    value = str(report.get(key, "")).lower() if key else ""
    return next((level for level, words in SEVERITY_WORDS.items() if any(w in value for w in words)), None)


def report_as_text(report_text):
    """Readable plain text for the downloaded report."""
    report = parse_report(report_text)
    if not report:
        return str(report_text or "")
    parts = []
    for key, value in report.items():
        if isinstance(value, list):
            body = "\n".join(f"- {v}" for v in value)
        elif isinstance(value, dict):
            body = "\n".join(f"- {k}: {v}" for k, v in value.items())
        else:
            body = str(value)
        parts.append(f"{key}\n{body}")
    return "\n\n".join(parts)


def extract_output(response, lang):
    try:
        data = response.json()
    except ValueError:
        return response.text.strip() or t(lang, "empty_response")

    def pick(item):
        found = next((item[k] for k in OUTPUT_KEYS if item.get(k) is not None), None)
        if found is None:
            return json.dumps(item, ensure_ascii=False, indent=2) if item else None
        return found if isinstance(found, str) else json.dumps(found, ensure_ascii=False, indent=2)

    if isinstance(data, list):
        parts = []
        for item in data:
            if isinstance(item, dict):
                p = pick(item)
                if p:
                    parts.append(p)
            else:
                parts.append(str(item))
        return "\n\n".join(parts) or t(lang, "no_report_in_response")

    if isinstance(data, dict):
        return pick(data) or t(lang, "no_report_in_response")

    return str(data)


def _error_detail(response):
    try:
        data = response.json()
    except ValueError:
        return response.text or ""
    if isinstance(data, dict) and (data.get("error") or data.get("message")):
        return str(data.get("error") or data.get("message"))
    return json.dumps(data, ensure_ascii=False)


def _post_workflow(payload, lang, timeout):
    """One attempt through n8n. Returns (ok, result_or_error, quota_spent)."""
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=(10, timeout))
    except requests.exceptions.ConnectionError:
        return False, t(lang, "err_connect", url=WEBHOOK_URL), False
    except requests.exceptions.Timeout:
        return False, t(lang, "err_timeout"), False
    except requests.exceptions.RequestException as exc:
        return False, t(lang, "err_request", err=exc), False

    if 200 <= r.status_code < 300:
        return True, extract_output(r, lang), False
    if r.status_code == 404:
        return False, f"{t(lang, 'err_not_active')}\n{_error_detail(r)}", False
    detail = _error_detail(r)
    if llm.looks_like_quota(r.status_code, detail):
        return False, detail, True
    return False, f"{t(lang, 'err_http', code=r.status_code)}\n{detail}", False


def send_to_n8n(payload, lang, timeout=REQUEST_TIMEOUT):
    """Run the workflow, moving to the next provider whenever one is out of quota.

    The workflow cannot retry by itself, so each provider is tried in turn until one answers.
    Every provider being spent is survivable: each is retried after its cooldown, so they keep
    rotating and the user's request still succeeds.
    """
    last_error = ""
    for provider in llm.candidates("text"):
        # provider_key names the env vars the workflow should read (LLM_<key>_URL and so on).
        attempt = dict(payload, provider_key=provider["index"])
        ok, result, spent = _post_workflow(attempt, lang, timeout)
        if ok or not spent:
            return ok, result
        # This provider is spent: set it aside and try the next one.
        llm.set_aside(provider["index"])
        last_error = result
    return False, f"{t(lang, 'err_http', code=429)}\n{last_error}"


def suggest_details(case_text, lang):
    """Title, type, location and date suggested from the report text. Empty dict when unavailable."""
    ok, result = send_to_n8n({"mode": "suggest", "case_text": case_text, "language": lang}, lang, timeout=60)
    data = parse_report(result) if ok else None
    if not data:
        return {}
    suggestion = {
        "case_name": str(data.get("title") or "").strip(),
        "case_type": data.get("case_type") if data.get("case_type") in CASE_TYPES else "",
        "location": str(data.get("location") or "").strip(),
        "date": str(data.get("date") or "").strip(),
    }
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", suggestion["date"]):
        suggestion["date"] = ""
    return {k: v for k, v in suggestion.items() if v}


def attachments_for_prompt(case_id, lang):
    """Text that carries the attachments into the analysis, plus what could not be read.

    Documents give their text directly. Images and video frames are described by the vision
    model first, because the analysis model may not accept images at all.
    """
    rows = db.list_attachments(case_id)
    if not rows:
        return "", [], 0
    cache = {r["id"]: r.get("description") for r in rows if r.get("description")}
    text, images = extract.describe(lang, rows, cache=cache)
    errors = []
    if images:
        described, errors = vision.describe_many(lang, images, cache=cache)
        text = "\n\n".join(part for part in (text, described) if part)
    if errors:
        text = "\n\n".join(part for part in (
            text, t(lang, "ex_skipped", names="; ".join(errors))) if part)
    return text, errors, len(images)


def _run_analysis(inv_id, lang):
    case = db.get_case(inv_id)
    if not case:
        return
    payload = case_payload(case, lang)
    attachment_text, _, _ = attachments_for_prompt(inv_id, lang)
    if attachment_text:
        payload["case_text"] = f"{payload.get('case_text') or ''}\n\n{attachment_text}".strip()
    ok, result = send_to_n8n(payload, lang)
    if not db.get_case(inv_id):  # deleted while it was being analyzed
        return
    if ok:
        db.save_analysis_report(inv_id, result, extract_severity(result))
    else:
        db.update_case(inv_id, status="failed", error=result)


def locate(inv_id, lang):
    """Pin the case on the map from its location text, unless someone has already placed it.

    Returns True when a pin was saved. Never raises: a place lookup is a convenience, and a
    failed one must not stop the case from being saved or analyzed.
    """
    case = db.get_case(inv_id)
    if not case or case["latitude"] is not None:
        return False
    point = geocode.find(case["location"] or "", lang)
    if not point:
        return False
    db.update_case(inv_id, latitude=point[0], longitude=point[1])
    return True


def start_analysis(inv_id, lang):
    """Mark the case as analyzing and analyze it on a background thread, so the page stays usable.

    The map pin is found first, so the case appears on the map about when it is saved.
    """
    case = db.get_case(inv_id)
    if case and case["latitude"] is None:
        locate(inv_id, lang)
    db.update_case(inv_id, status="analyzing", error=None)
    threading.Thread(target=_run_analysis, args=(inv_id, lang), daemon=True).start()


def check_n8n(lang):
    """Ping the workflow itself (not just the n8n server). Returns (level, message)."""
    try:
        r = requests.post(WEBHOOK_URL, json={"ping": True}, timeout=10)
    except requests.exceptions.RequestException:
        return "error", t(lang, "chk_unreachable", url=WEBHOOK_URL)

    if r.status_code == 404:
        return "error", t(lang, "chk_not_active")
    if not 200 <= r.status_code < 300:
        return "error", t(lang, "chk_error", code=r.status_code, detail=_error_detail(r))

    try:
        data = r.json()
    except ValueError:
        data = None
    if not (isinstance(data, dict) and data.get("ok")):
        return "success", t(lang, "chk_custom")
    if not data.get("llm_configured"):
        return "warning", t(lang, "chk_no_key")
    state = llm.status()
    spent = [p for p in state["providers"] if p["set_aside_s"]]
    if spent and len(spent) < state["count"]:
        # Some providers are out of quota but at least one is still answering.
        active = next(p["model"] for p in state["providers"] if not p["set_aside_s"])
        return "warning", t(lang, "provider_switched", model=active,
                            n=len(spent), total=state["count"])
    if spent:
        minutes = max(1, min(p["set_aside_s"] for p in spent) // 60)
        return "warning", t(lang, "provider_all_spent", n=state["count"], minutes=minutes)
    return "success", t(lang, "chk_ok", model=state["main_model"] or "—")
    return "success", t(lang, "chk_ok", model=data.get("model") or "—")
