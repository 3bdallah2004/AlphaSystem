"""The investigator's conversation with Alpha: one conversation about every case.

Each turn is sent to the analysis workflow with an overview of the whole case register, the
full details of the case the investigator had open when asking (if any), and the conversation
so far, so the reply can build on everything said before. Files attached to a message are read
the same way case attachments are (documents give text, images and video frames are described
by the vision model).

A reply may also propose a change to the register (a new case, an update, an analysis); see
chat_actions.py. Cases named in the question by number get their full details in the prompt.
"""
import json
import hashlib
import logging
import re
import threading
import time

import attachments
import chat_actions
import db
import extract
import vision
from analysis import parse_report, report_as_text, send_to_n8n
from config import ALPHA_WORKER
from i18n import t

log = logging.getLogger(__name__)

# The conversation is not about one case, so its messages and their files are stored under this
# id, which no case has (case ids start at 1).
GLOBAL_CHAT = 0

MAX_HISTORY = 20          # messages sent as context, oldest dropped first
MAX_REPORT_CHARS = 8000   # the open case's report
MAX_SUMMARY_CHARS = 600   # each case's summary in the register overview
MAX_OVERVIEW_CHARS = 30000
MAX_REFERENCED = 3        # cases named in the question that get their full details
MAX_REFERENCED_CHARS = 4000
# Case numbers as the app writes them (ALP-2026-006), and ids written as #87.
CASE_REF_RE = re.compile(r"\b[A-Za-z]{2,10}-\d{4}-\d+\b|#\d+")


def _turn_text(message):
    """A message as the model sees it: its text, plus what became of any change it proposed."""
    note = chat_actions.history_note(chat_actions.load(message))
    return "\n".join(part for part in ((message["content"] or "").strip(), note) if part)


def history(limit=MAX_HISTORY, before_id=None):
    """The conversation as [{role, content}], with unreadable turns left out."""
    turns = []
    for message in db.chat_history_rows(GLOBAL_CHAT, before_id):
        content = _turn_text(message)
        if content:
            turns.append({"role": "user" if message["role"] == "user" else "assistant", "content": content})
        if len(turns) >= limit:
            break
    return list(reversed(turns))


def message_attachment_text(lang, message_id):
    """What a message's own attachments say, as text for the prompt."""
    rows = db.list_message_attachments(message_id)
    if not rows:
        return "", []
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
    log.info("AI timing phase=chat_attachments message_id=%s files=%d images=%d elapsed_seconds=%.2f",
             message_id, len(rows), len(images), time.perf_counter() - started)
    return text, errors


def _one_line(text, limit):
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def cases_overview(lang, focus_case_id=None):
    """Every case in a few lines, newest first, so questions can span the whole register."""
    en = lang == "en"
    blocks = []
    length = 0
    for case in db.chat_case_rows():
        report = case.get("report_text") or ""
        lines = [
            f"#{case['id']} · {case.get('case_number') or '—'} · {case.get('case_name') or '—'}",
            (f"Type: {case.get('case_type') or '—'} | Status: {case.get('status') or '—'} | "
             f"Severity: {case.get('severity') or '—'}" if en else
             f"التصنيف: {case.get('case_type') or '—'} | الحالة: {case.get('status') or '—'} | "
             f"الخطورة: {case.get('severity') or '—'}"),
            (f"Location: {case.get('location') or '—'} | Date: {case.get('date') or '—'} | "
             f"Added: {case.get('timestamp') or '—'}" if en else
             f"الموقع: {case.get('location') or '—'} | التاريخ: {case.get('date') or '—'} | "
             f"أُضيفت: {case.get('timestamp') or '—'}"),
        ]
        if case["id"] == focus_case_id:
            lines.append("Full source and analysis supplied separately." if en else "نص البلاغ والتحليل الكامل مرفقان بشكل منفصل.")
        elif report:
            label = "Analysis" if en else "التحليل"
            lines.append(f"{label}: {_one_line(report_as_text(report), MAX_SUMMARY_CHARS)}")
        else:
            label = "Report" if en else "البلاغ"
            lines.append(f"{label}: {_one_line(case.get('case_text'), MAX_SUMMARY_CHARS)}")
        blocks.append("\n".join(lines))
        length += len(blocks[-1]) + 2
        if length >= MAX_OVERVIEW_CHARS:
            break
    if not blocks:
        return "No cases are registered yet." if en else "لا توجد قضايا مسجلة بعد."
    text = "\n\n".join(blocks)
    return text[:MAX_OVERVIEW_CHARS]


def referenced_cases(question, exclude_id=None):
    """Cases the question names by number or #id, in the order named, without duplicates."""
    found = []
    for ref in CASE_REF_RE.findall(question or ""):
        case = chat_actions.find_case(ref)
        if case and case["id"] != exclude_id and case["id"] not in {c["id"] for c in found}:
            found.append(case)
        if len(found) == MAX_REFERENCED:
            break
    return found


def case_details(lang, case):
    """One case in full, for a question that names it: its latest state and report."""
    en = lang == "en"
    versions = db.list_report_versions(case["id"])
    files = db.list_case_files(case["id"])
    report = case.get("report_text") or ""
    lines = [
        f"#{case['id']} · {case.get('case_number') or '—'} · {case.get('case_name') or '—'}",
        (f"Type: {case.get('case_type') or '—'} | Status: {case.get('status') or '—'} | "
         f"Severity: {case.get('severity') or '—'}" if en else
         f"التصنيف: {case.get('case_type') or '—'} | الحالة: {case.get('status') or '—'} | "
         f"الخطورة: {case.get('severity') or '—'}"),
        (f"Location: {case.get('location') or '—'} | Incident date: {case.get('date') or '—'} | "
         f"Added: {case.get('timestamp') or '—'}" if en else
         f"الموقع: {case.get('location') or '—'} | تاريخ الحادثة: {case.get('date') or '—'} | "
         f"أُضيفت: {case.get('timestamp') or '—'}"),
        (f"Attachments: {len(files)} | Earlier report versions: {len(versions)}"
         + (f" (latest replaced {versions[-1]['timestamp']})" if versions else "") if en else
         f"المرفقات: {len(files)} | نسخ التقرير السابقة: {len(versions)}"
         + (f" (آخرها استُبدل في {versions[-1]['timestamp']})" if versions else "")),
    ]
    if case.get("error"):
        lines.append(f"{'Last error' if en else 'آخر خطأ'}: {_one_line(case['error'], 300)}")
    lines.append(f"{'Original report' if en else 'نص البلاغ'}:\n{case.get('case_text') or ''}")
    if report:
        text = report_as_text(report) if parse_report(report) else report
        lines.append(f"{'Analysis' if en else 'التحليل'}:\n{text}")
    return "\n".join(lines)[:MAX_REFERENCED_CHARS]


def build_payload(lang, question, message_id=None, focus_case_id=None):
    """Everything the workflow needs to answer one turn."""
    earlier = history(before_id=message_id)
    # The current question is sent on its own, so drop it from the history it also appears in.
    if message_id is None and earlier and earlier[-1]["role"] == "user" and earlier[-1]["content"] == question:
        earlier = earlier[:-1]
    focus = db.get_case(focus_case_id) if focus_case_id else None
    report_text = (focus or {}).get("report_text") or ""
    payload = {
        "mode": "chat",
        "language": lang,
        "cases_overview": cases_overview(lang, focus_case_id),
        "focus_case_id": focus["id"] if focus else None,
        "case_name": (focus or {}).get("case_name") or "",
        "case_number": (focus or {}).get("case_number") or "",
        "case_type": (focus or {}).get("case_type") or "",
        "incident_location": (focus or {}).get("location") or "",
        "incident_date": (focus or {}).get("date") or "",
        "case_text": (focus or {}).get("case_text") or "",
        "report_text": (report_as_text(report_text) if parse_report(report_text) else
                        report_text)[:MAX_REPORT_CHARS],
        "referenced_cases": "\n\n".join(
            case_details(lang, case)
            for case in referenced_cases(question, exclude_id=focus["id"] if focus else None)),
        "question": question,
        "history": earlier,
    }
    if message_id:
        attached, errors = message_attachment_text(lang, message_id)
        if attached:
            payload["question"] = f"{question}\n\n{attached}".strip()
        payload["attachment_errors"] = errors
    return payload


def _run_reply(reply_id, lang):
    """The background job. Whatever goes wrong, the reply ends as ok or failed, never pending."""
    try:
        _write_reply(reply_id, lang)
    except Exception as exc:  # an unexpected error must not leave the reply "writing" forever
        log.exception("Reply %s failed", reply_id)
        try:
            if db.get_message(reply_id):
                db.update_message(reply_id, status="failed", error=t(lang, "err_unexpected", err=exc))
        except Exception:
            log.exception("Could not mark reply %s as failed", reply_id)


def _write_reply(reply_id, lang):
    """Write the reply to reply_id, reading the files of the question it answers."""
    reply = db.get_message(reply_id)
    if not reply:
        return
    question = db.get_message(reply.get("reply_to")) if reply.get("reply_to") else None
    text = (question or reply)["content"] or ""
    payload = build_payload(lang, text, question["id"] if question else None,
                            focus_case_id=(question or {}).get("focus_case_id"))
    ok, result = send_to_n8n(payload, lang)
    if not db.get_message(reply_id):   # the conversation was cleared while the reply was written
        return
    if ok:
        content, proposal = chat_actions.split_reply(result)
        action = chat_actions.propose(proposal, lang) if proposal is not None else None
        db.update_message(reply_id, content=content, status="ok", error=None,
                          action=json.dumps(action, ensure_ascii=False) if action else None)
    else:
        db.update_message(reply_id, status="failed", error=result)


def ask(question, lang, uploaded=None, focus_case_id=None, request_id=None):
    """Record the question, its files, and start writing the reply on a background thread.

    focus_case_id is the case the investigator had open when asking; the reply gets its full
    details on top of the register overview, so "this case" means something.
    """
    fingerprint = hashlib.sha256(json.dumps([question, lang, focus_case_id,
        [(item.name, hashlib.sha256(item.getvalue()).hexdigest()) for item in (uploaded or [])]],
        ensure_ascii=False).encode()).hexdigest()
    message_id, reply_id, created = db.create_chat_turn(
        GLOBAL_CHAT, question, ALPHA_WORKER, focus_case_id, request_id, fingerprint)
    if not created:
        return message_id, reply_id, len(db.list_message_attachments(message_id)), []
    saved, errors = 0, []
    for item in (uploaded or []):
        ok, reason = _save_file(message_id, item, lang)
        if ok:
            saved += 1
        else:
            errors.append(f"{item.name}: {reason}")
    threading.Thread(target=_run_reply, args=(reply_id, lang), daemon=True).start()
    return message_id, reply_id, saved, errors


def _save_file(message_id, uploaded, lang):
    """Returns (ok, message). The failure keys are the only ones that need formatting."""
    ok, reason = attachments.save(GLOBAL_CHAT, uploaded, message_id=message_id)
    if ok:
        return True, ""
    return False, t(lang, reason, mb=attachments.MAX_ATTACHMENT_MB)


def messages():
    """The conversation, each message with its files."""
    rows = db.list_messages(GLOBAL_CHAT)
    files = {}
    for item in db.chat_attachment_rows(GLOBAL_CHAT):
        files.setdefault(item["message_id"], []).append(item)
    for message in rows:
        message["attachments"] = files.get(message["id"], [])
        message["action"] = chat_actions.load(message)
    return rows


def retry(reply_id, lang):
    if not db.claim_reply_retry(reply_id, ALPHA_WORKER):
        return
    threading.Thread(target=_run_reply, args=(reply_id, lang), daemon=True).start()


def clear():
    """Remove the conversation and the files that came with it."""
    for message in db.list_messages(GLOBAL_CHAT):
        for row in db.list_message_attachments(message["id"]):
            attachments.remove(row)
    db.delete_messages(GLOBAL_CHAT)
