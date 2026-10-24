"""The conversation about a case: the investigator's questions, notes and new material.

Each turn is sent to the analysis workflow with the case report, the current analysis and the
conversation so far, so the reply can build on everything said before. Files attached to a
message are read the same way case attachments are (documents give text, images and video
frames are described by the vision model).
"""
import threading

import attachments
import db
import extract
import vision
from analysis import parse_report, report_as_text, send_to_n8n
from i18n import t

MAX_HISTORY = 20          # messages sent as context, oldest dropped first
MAX_REPORT_CHARS = 8000


def history(case_id, limit=MAX_HISTORY):
    """The conversation as [{role, content}], with unreadable turns left out."""
    rows = [m for m in db.list_messages(case_id) if m["status"] == "ok" and (m["content"] or "").strip()]
    return [{"role": "user" if m["role"] == "user" else "assistant", "content": m["content"]}
            for m in rows[-limit:]]


def message_attachment_text(lang, message_id):
    """What a message's own attachments say, as text for the prompt."""
    rows = db.list_message_attachments(message_id)
    if not rows:
        return "", []
    cache = {r["id"]: r.get("description") for r in rows if r.get("description")}
    text, images = extract.describe(lang, rows, cache=cache)
    errors = []
    if images:
        described, errors = vision.describe_many(lang, images, cache=cache)
        text = "\n\n".join(part for part in (text, described) if part)
        if errors:
            text = "\n\n".join(part for part in (
                text, t(lang, "ex_skipped", names="; ".join(errors))) if part)
    return text, errors


def build_payload(case, lang, question, message_id=None):
    """Everything the workflow needs to answer one turn."""
    report = parse_report(case.get("report_text")) if case.get("report_text") else None
    earlier = history(case["id"])
    # The current question is sent on its own, so drop it from the history it also appears in.
    if earlier and earlier[-1]["role"] == "user" and earlier[-1]["content"] == question:
        earlier = earlier[:-1]
    payload = {
        "mode": "chat",
        "language": lang,
        "case_name": case.get("case_name") or "",
        "case_number": case.get("case_number") or "",
        "case_type": case.get("case_type") or "",
        "incident_location": case.get("location") or "",
        "incident_date": case.get("date") or "",
        "case_text": case.get("case_text") or "",
        "report_text": (report_as_text(case.get("report_text")) if report else
                        (case.get("report_text") or ""))[:MAX_REPORT_CHARS],
        "question": question,
        "history": earlier,
    }
    if message_id:
        attached, errors = message_attachment_text(lang, message_id)
        if attached:
            payload["question"] = f"{question}\n\n{attached}".strip()
        payload["attachment_errors"] = errors
    return payload


def _run_reply(case_id, reply_id, lang):
    """Write the reply to reply_id, reading the files of the question it answers."""
    case = db.get_case(case_id)
    reply = db.get_message(reply_id)
    if not case or not reply:
        return
    question = db.get_message(reply.get("reply_to")) if reply.get("reply_to") else None
    text = (question or reply)["content"] or ""
    payload = build_payload(case, lang, text, question["id"] if question else None)
    ok, result = send_to_n8n(payload, lang)
    if not db.get_message(reply_id):   # the conversation was cleared while the reply was written
        return
    if ok:
        db.update_message(reply_id, content=result, status="ok", error=None)
    else:
        db.update_message(reply_id, status="failed", error=result)


def ask(case_id, question, lang, uploaded=None):
    """Record the question, its files, and start writing the reply on a background thread."""
    message_id = db.add_message(case_id, "user", question)
    saved, errors = 0, []
    for item in (uploaded or []):
        ok, reason = _save_file(case_id, message_id, item, lang)
        if ok:
            saved += 1
        else:
            errors.append(f"{item.name}: {reason}")
    reply_id = db.add_message(case_id, "assistant", "", status="pending", reply_to=message_id)
    threading.Thread(target=_run_reply, args=(case_id, reply_id, lang), daemon=True).start()
    return message_id, reply_id, saved, errors


def _save_file(case_id, message_id, uploaded, lang):
    """Returns (ok, message). The failure keys are the only ones that need formatting."""
    ok, reason = attachments.save(case_id, uploaded, message_id=message_id)
    if ok:
        return True, ""
    return False, t(lang, reason, mb=attachments.MAX_ATTACHMENT_MB)


def retry(case_id, reply_id, lang):
    db.update_message(reply_id, status="pending", error=None, content="")
    threading.Thread(target=_run_reply, args=(case_id, reply_id, lang), daemon=True).start()


def clear(case_id):
    """Remove the conversation and the files that came with it, keeping case attachments."""
    for message in db.list_messages(case_id):
        for row in db.list_message_attachments(message["id"]):
            attachments.remove(row)
    db.delete_messages(case_id)
