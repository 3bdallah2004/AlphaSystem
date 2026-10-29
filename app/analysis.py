"""Client for the n8n analysis workflow (n8n/workflows/alpha-analysis.json)."""
import json
import hashlib
import itertools
import logging
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from datetime import date

import http_pool as requests

import db
import extract
import geocode
import llm
import vision
from config import ALPHA_WORKER, REQUEST_TIMEOUT, WEBHOOK_TOKEN, WEBHOOK_URL
from i18n import CASE_TYPES, case_type_label, t

log = logging.getLogger(__name__)
_analysis_lock = threading.RLock()
_analysis_generations = {}
_analysis_inputs = {}
_generation_sequence = itertools.count(1)
_suggest_lock = threading.Lock()
_suggest_cache = OrderedDict()
_suggest_pending = {}
SUGGEST_CACHE_TTL = 300
SUGGEST_CACHE_LIMIT = 128
SUGGEST_PROMPT_VERSION = 1


def _processing_signature():
    # Credentials participate only in a digest; no private input or key is logged.
    config = (WEBHOOK_URL, WEBHOOK_TOKEN, llm.PROVIDERS, SUGGEST_PROMPT_VERSION)
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()

OUTPUT_KEYS = ["output", "المخرجات", "report", "result", "response", "text", "message"]
CODE_FENCE_RE = re.compile(r"^```[a-zA-Z]*\s*(.*?)\s*```$", re.S)
SEVERITY_WORDS = {
    "high": ("مرتفع", "عال", "high", "critical"),
    "medium": ("متوسط", "medium", "moderate"),
    "low": ("منخفض", "low"),
}
# A level word right after one of these ("not high", "غير مرتفعة") does not name the level.
NEGATIONS = {"not", "non", "no", "غير", "ليس", "ليست", "لا"}
_ARABIC_LETTER = "\u0600-\u06FF"


def _level_pattern(word):
    if word.isascii():
        return re.compile(rf"\b{re.escape(word)}")
    # Arabic: a whole word, allowing the article and "و" in front ("العالية", "ومرتفعة").
    return re.compile(rf"(?<![{_ARABIC_LETTER}])(?:و?ال|و)?{re.escape(word)}")


SEVERITY_PATTERNS = [(level, _level_pattern(word))
                     for level, words in SEVERITY_WORDS.items() for word in words]


def case_payload(case, language):
    case_text = case["case_text"] or ""
    current_report = (case.get("report_text") or "").strip()
    if current_report:
        if language == "en":
            case_text = (
                f"Updated original report (authoritative source):\n{case_text}\n\n"
                f"Previous analysis (context only; re-evaluate it against the updated source):\n"
                f"{current_report}\n\n"
                "Generate a fresh report from the updated original report and all current "
                "attachments. Incorporate new information, correct outdated conclusions, "
                "and do not copy the previous analysis without re-evaluating it."
            ).strip()
        else:
            case_text = (
                f"نص البلاغ الأصلي المحدّث (المصدر المعتمد):\n{case_text}\n\n"
                f"التحليل السابق (للسياق فقط؛ أعد تقييمه وفق النص المحدّث):\n"
                f"{current_report}\n\n"
                "أنشئ تقريراً جديداً اعتماداً على نص البلاغ المحدّث وجميع المرفقات الحالية. "
                "أدرج المعلومات الجديدة وصحّح الاستنتاجات القديمة، ولا تنسخ التحليل السابق "
                "دون إعادة تقييمه."
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


def severity_level(value):
    """The level a severity text names: the first level word that is not negated, else None."""
    text = str(value or "").lower()
    hits = []
    for level, pattern in SEVERITY_PATTERNS:
        for match in pattern.finditer(text):
            # Only the word right before counts: "not high" is negated, "non-critical; low" is low.
            before = text[:match.start()].replace("-", "- ").split()[-1:]
            if before and before[0].strip("-—–:،,.()") in NEGATIONS:
                continue
            hits.append((match.start(), level))
    return min(hits)[1] if hits else None


def extract_severity(report_text):
    report = parse_report(report_text)
    if not report:
        return None
    key = find_key(report, "خطورة", "severity")
    return severity_level(report.get(key)) if key else None


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


def _headers():
    """The shared secret the workflow checks, when one is configured."""
    return {"X-Alpha-Token": WEBHOOK_TOKEN} if WEBHOOK_TOKEN else {}


def _post_workflow(payload, lang, timeout):
    """One attempt through n8n. Returns (ok, result_or_error, quota_spent)."""
    try:
        r = requests.post(WEBHOOK_URL, json=payload, headers=_headers(), timeout=(10, timeout))
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
    if r.status_code == 401:
        return False, t(lang, "err_unauthorized"), False
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
    providers = llm.candidates("text")
    if not providers:
        # Nothing to send the request to: say so, instead of a quota error that never happened.
        return False, t(lang, "err_no_provider")
    last_error = ""
    mode = payload.get("mode")
    if mode not in {"analysis", "chat", "suggest"}:
        mode = "analysis"
    for provider in providers:
        # provider_key names the env vars the workflow should read (LLM_<key>_URL and so on).
        attempt = dict(payload, provider_key=provider["index"])
        started = time.perf_counter()
        ok, result, spent = _post_workflow(attempt, lang, timeout)
        if ok or not spent:
            log.info("AI timing mode=%s provider=%s outcome=%s elapsed_seconds=%.2f",
                     mode, provider["index"], "success" if ok else "failed",
                     time.perf_counter() - started)
            return ok, result
        # This provider is spent: set it aside and try the next one.
        log.info("AI timing mode=%s provider=%s outcome=quota_retry elapsed_seconds=%.2f",
                 mode, provider["index"], time.perf_counter() - started)
        llm.set_aside(provider["index"])
        last_error = result
    return False, f"{t(lang, 'err_quota_all')}\n{last_error}".strip()


def _suggest_details(case_text, lang):
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
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", suggestion["date"]):
            raise ValueError("Not an ISO date")
        date.fromisoformat(suggestion["date"])
    except ValueError:
        suggestion["date"] = ""
    return {k: v for k, v in suggestion.items() if v}


def suggest_details(case_text, lang, case_id=None):
    """Reuse successful extraction only for the same case, exact source and configuration.

    Concurrent identical requests share one call; failures are not cached. Standalone callers
    without a case scope remain uncached so results can never cross case boundaries.
    """
    if case_id is None:
        return _suggest_details(case_text, lang)
    key = (str(db.DB_PATH), case_id, lang, _processing_signature(),
           hashlib.sha256(case_text.encode()).hexdigest())
    started = time.perf_counter()
    with _suggest_lock:
        cached = _suggest_cache.get(key)
        if cached and time.monotonic() - cached[0] < SUGGEST_CACHE_TTL:
            _suggest_cache.move_to_end(key)
            log.info("AI timing mode=suggest case_id=%s outcome=cache_hit elapsed_seconds=%.4f",
                     case_id, time.perf_counter() - started)
            return dict(cached[1])
        _suggest_cache.pop(key, None)
        future = _suggest_pending.get(key)
        owner = future is None
        if owner:
            future = _suggest_pending[key] = Future()
    if not owner:
        return dict(future.result())
    try:
        result = _suggest_details(case_text, lang)
        with _suggest_lock:
            if result:
                _suggest_cache[key] = (time.monotonic(), dict(result))
                while len(_suggest_cache) > SUGGEST_CACHE_LIMIT:
                    _suggest_cache.popitem(last=False)
        future.set_result(result)
        return dict(result)
    except Exception as exc:
        future.set_exception(exc)
        raise
    finally:
        with _suggest_lock:
            _suggest_pending.pop(key, None)


def attachments_for_prompt(case_id, lang):
    """Text that carries the attachments into the analysis, plus what could not be read.

    Documents give their text directly. Images and video frames are described by the vision
    model first, because the analysis model may not accept images at all.
    """
    rows = db.list_attachments(case_id)
    if not rows:
        return "", [], 0
    started = time.perf_counter()
    cache = {r["id"]: r.get("description") for r in rows if r.get("description")}
    text, images = extract.describe(lang, rows, cache=cache)
    errors = []
    if images:
        described, errors = vision.describe_many(lang, images, cache=cache)
        text = "\n\n".join(part for part in (text, described) if part)
    if errors:
        text = "\n\n".join(part for part in (
            text, t(lang, "ex_skipped", names="; ".join(errors))) if part)
    log.info("AI timing phase=analysis_attachments case_id=%s files=%d images=%d elapsed_seconds=%.2f",
             case_id, len(rows), len(images), time.perf_counter() - started)
    return text, errors, len(images)


def _is_current_analysis(inv_id, generation):
    if generation is None:
        return True
    with _analysis_lock:
        return _analysis_generations.get(inv_id) == generation


def _run_analysis(inv_id, lang, generation=None):
    """The background job. Whatever goes wrong, the case ends as analyzed or failed, never stuck."""
    try:
        _analyze(inv_id, lang, generation)
    except Exception as exc:  # an unexpected error must not leave the case "analyzing" forever
        log.exception("Analysis of case %s failed", inv_id)
        try:
            if _is_current_analysis(inv_id, generation) and db.get_case(inv_id):
                db.update_case(inv_id, status="failed", error=t(lang, "err_unexpected", err=exc))
        except Exception:
            log.exception("Could not mark case %s as failed", inv_id)
    finally:
        if generation is not None:
            with _analysis_lock:
                if _analysis_generations.get(inv_id) == generation:
                    del _analysis_generations[inv_id]
                    _analysis_inputs.pop(inv_id, None)


def _analyze(inv_id, lang, generation=None):
    started = time.perf_counter()
    if not _is_current_analysis(inv_id, generation):
        return
    case = db.get_case(inv_id)
    if not case:
        return
    if case["latitude"] is None:
        locate_later(inv_id, lang)
    payload = case_payload(case, lang)
    attachment_text, _, _ = attachments_for_prompt(inv_id, lang)
    if attachment_text:
        payload["case_text"] = f"{payload.get('case_text') or ''}\n\n{attachment_text}".strip()
    ok, result = send_to_n8n(payload, lang)
    if not db.get_case(inv_id):  # deleted while it was being analyzed
        log.info("AI timing mode=analysis case_id=%s outcome=deleted elapsed_seconds=%.2f",
                 inv_id, time.perf_counter() - started)
        return
    with _analysis_lock:
        if not _is_current_analysis(inv_id, generation):
            log.info("AI timing mode=analysis case_id=%s outcome=superseded elapsed_seconds=%.2f",
                     inv_id, time.perf_counter() - started)
            return
        if ok:
            db.save_analysis_report(inv_id, result, extract_severity(result))
        else:
            db.update_case(inv_id, status="failed", error=result)
    log.info("AI timing mode=analysis case_id=%s outcome=%s elapsed_seconds=%.2f",
             inv_id, "success" if ok else "failed", time.perf_counter() - started)


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
    # A slow lookup must not replace a pin or location edited while it was in flight.
    with db.db() as conn:
        cursor = conn.execute(
            "UPDATE investigations SET latitude=?, longitude=? "
            "WHERE id=? AND latitude IS NULL AND longitude IS NULL AND location IS ?",
            (point[0], point[1], inv_id, case["location"]),
        )
        return cursor.rowcount > 0


_locate_jobs_lock = threading.Lock()
_locate_jobs = set()


def locate_later(inv_id, lang):
    """Optional map enrichment never holds up a save or completed AI analysis."""
    case = db.get_case(inv_id)
    if not case or case["latitude"] is not None or not case.get("location"):
        return False
    key = (str(db.DB_PATH), inv_id, case["location"], lang)
    with _locate_jobs_lock:
        if key in _locate_jobs:
            return False
        _locate_jobs.add(key)

    def work():
        started = time.perf_counter()
        try:
            locate(inv_id, lang)
        except Exception:
            log.exception("Could not locate case %s", inv_id)
        finally:
            with _locate_jobs_lock:
                _locate_jobs.discard(key)
            log.info("AI timing phase=geocode case_id=%s elapsed_seconds=%.2f",
                     inv_id, time.perf_counter() - started)

    threading.Thread(target=work, daemon=True).start()
    return True


_locate_lock = threading.Lock()
_locate_tried = set()       # cases already looked up in this run: a failed lookup is not repeated
_locate_running = False


def locate_missing(case_ids, lang, limit=3):
    """Pin cases that have no coordinates, on a background thread so the page never waits.

    Each case is looked up at most once per app run, and only `limit` per call, so a big register
    does not flood the place-lookup service. Returns True when a lookup was started.
    """
    global _locate_running
    with _locate_lock:
        if _locate_running:
            return False
        pending = [case_id for case_id in case_ids if case_id not in _locate_tried][:limit]
        if not pending:
            return False
        _locate_tried.update(pending)
        _locate_running = True

    def work():
        global _locate_running
        try:
            for case_id in pending:
                try:
                    locate(case_id, lang)
                except Exception:
                    log.exception("Could not locate case %s", case_id)
        finally:
            with _locate_lock:
                _locate_running = False

    threading.Thread(target=work, daemon=True).start()
    return True


def start_analysis(inv_id, lang):
    """Mark the case as analyzing and analyze it on a background thread, so the page stays usable."""
    with _analysis_lock:
        case = db.get_case(inv_id)
        if not case:
            return False
        files = db.list_attachments(inv_id)
        source = {k: case.get(k) for k in (
            "case_text", "case_name", "case_number", "case_type", "location", "date", "report_text")}
        source["attachments"] = [{k: item.get(k) for k in (
            "id", "file_name", "stored_name", "mime_type", "size", "kind")} for item in files]
        signature = (str(db.DB_PATH), lang, _processing_signature(),
                     hashlib.sha256(json.dumps(source, sort_keys=True).encode()).hexdigest())
        if inv_id in _analysis_generations and _analysis_inputs.get(inv_id) == signature:
            return False
        generation = next(_generation_sequence)
        _analysis_generations[inv_id] = generation
        _analysis_inputs[inv_id] = signature
        db.update_case(inv_id, status="analyzing", error=None, worker=ALPHA_WORKER)
    threading.Thread(target=_run_analysis, args=(inv_id, lang, generation), daemon=True).start()
    return True


def check_n8n(lang):
    """Ping the workflow itself (not just the n8n server). Returns (level, message)."""
    try:
        r = requests.post(WEBHOOK_URL, json={"ping": True}, headers=_headers(), timeout=10)
    except requests.exceptions.RequestException:
        return "error", t(lang, "chk_unreachable", url=WEBHOOK_URL)

    if r.status_code == 404:
        return "error", t(lang, "chk_not_active")
    if r.status_code == 401:
        return "error", t(lang, "chk_unauthorized")
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
    return "success", t(lang, "chk_ok", model=state["main_model"] or data.get("model") or "—")
