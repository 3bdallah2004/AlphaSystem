"""Changes to the case register that the investigator asks for in the conversation.

The model never changes anything itself. A reply that proposes a change ends with an
<alpha-action> block; the block is checked here and stored on the reply as a pending action,
and the change is made only when the investigator confirms it. Every value is checked again at
that moment, because the case may have changed in between.

An action is a dict stored as JSON on the reply:
    type      create_case | update_case | analyze_case
    status    pending -> applying -> confirmed | failed, or pending -> cancelled;
              invalid when the proposal itself could not be accepted
    case_id, case_number, case_name   the case it concerns (the new case once created)
    fields    the validated new values
    changes   [{field, before, after}] for display and to detect conflicting edits
    append_text   text added to the end of the incident report
    error     why it is invalid or failed
"""
import datetime
import json
import logging
import re
import threading

import analysis
import db
from i18n import CASE_TYPE_EN, CASE_TYPES, SEVERITIES, t

log = logging.getLogger(__name__)

KINDS = ("create_case", "update_case", "analyze_case")
ACTION_RE = re.compile(r"<alpha-action>\s*(.*?)\s*</alpha-action>", re.S | re.I)
FENCED_ACTION_RE = re.compile(r"```alpha-action\s*(.*?)```", re.S | re.I)

# Fields the conversation may change. Status follows the analysis, so it changes through
# analyze_case; the report, coordinates and bookkeeping columns are never set from chat.
FIELDS = ("case_name", "case_number", "case_type", "location", "date", "case_text", "severity")
MAX_LENGTH = {"case_name": 200, "case_number": 50, "case_type": 50, "location": 300, "date": 10,
              "case_text": 20000, "severity": 50}
MAX_APPEND = 10000
MIN_CASE_TEXT = 20    # the same minimum as a case created from the form


class Invalid(Exception):
    """A proposal or confirmation that cannot go ahead; the message is shown to the investigator."""


def split_reply(text):
    """The reply without its action block, and the block as a dict (None when there is none).

    An unreadable block gives {} so it is reported as an invalid proposal rather than lost.
    """
    text = text or ""
    found = [m for pattern in (ACTION_RE, FENCED_ACTION_RE) for m in pattern.finditer(text)]
    if not found:
        return text.strip(), None
    raw = max(found, key=lambda m: m.start()).group(1).strip()
    fenced = analysis.CODE_FENCE_RE.match(raw)
    if fenced:
        raw = fenced.group(1)
    for pattern in (ACTION_RE, FENCED_ACTION_RE):
        text = pattern.sub("", text)
    try:
        data = json.loads(raw)
    except ValueError:
        data = {}
    return text.strip(), data if isinstance(data, dict) else {}


def find_case(ref):
    """A case by its number ("ALP-2026-006") or id ("#87", 87). None when there is no such case."""
    text = str(ref if ref is not None else "").strip()
    if not text:
        return None
    by_number = db.find_case_by_number(text)
    if by_number:
        return by_number
    match = re.fullmatch(r"#?(\d+)", text)
    return db.get_case(int(match.group(1))) if match else None


def _label(lang, field):
    return t(lang, f"fld_{field}")


def _check(name, value, lang, case_id):
    """One field's value as it will be stored. Raises Invalid with a reason the investigator can act on."""
    if name == "case_text":
        if len(value) < MIN_CASE_TEXT:
            raise Invalid(t(lang, "act_case_text_short"))
        return value
    if name == "case_type":
        if value in CASE_TYPES:
            return value
        by_english = {label.lower(): key for key, label in CASE_TYPE_EN.items()}
        if value.lower() in by_english:
            return by_english[value.lower()]
        names = ", ".join(CASE_TYPE_EN[k] if lang == "en" else k for k in CASE_TYPES)
        raise Invalid(t(lang, "act_bad_type", types=names))
    if name == "date":
        if not value:
            return ""
        try:
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                raise ValueError(value)
            datetime.date.fromisoformat(value)
        except ValueError:
            raise Invalid(t(lang, "act_bad_date")) from None
        return value
    if name == "severity":
        if not value:
            return None
        level = value.lower() if value.lower() in SEVERITIES else analysis.severity_level(value)
        if not level:
            raise Invalid(t(lang, "act_bad_severity"))
        return level
    if name == "case_number":
        if not value:
            raise Invalid(t(lang, "act_need_number"))
        if db.case_number_exists(value, exclude_id=case_id):
            raise Invalid(t(lang, "act_duplicate_number", number=value))
        return value
    return value   # case_name, location: free text


def clean_fields(fields, lang, case_id=None):
    """The proposed fields, validated and normalized. case_id is the case being updated, if any."""
    if not isinstance(fields, dict):
        raise Invalid(t(lang, "act_bad_fields"))
    unknown = sorted(set(fields) - set(FIELDS))
    if "status" in unknown:
        raise Invalid(t(lang, "act_status_readonly"))
    if unknown:
        raise Invalid(t(lang, "act_unknown_fields", names=", ".join(unknown)))
    clean = {}
    for name in FIELDS:
        if name not in fields:
            continue
        value = fields[name]
        if value is None:
            value = ""
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise Invalid(t(lang, "act_bad_value", field=_label(lang, name)))
        value = str(value).strip()
        if len(value) > MAX_LENGTH[name]:
            raise Invalid(t(lang, "act_too_long", field=_label(lang, name)))
        clean[name] = _check(name, value, lang, case_id)
    return clean


def _same(a, b):
    return (a or "") == (b or "")


def _target(case):
    return {"case_id": case["id"], "case_number": case.get("case_number") or "",
            "case_name": case.get("case_name") or ""}


def _plan_create(data, lang):
    fields = {k: v for k, v in clean_fields(data.get("fields") or {}, lang).items() if v not in ("", None)}
    if not fields.get("case_text"):
        raise Invalid(t(lang, "act_need_case_text"))
    return {"type": "create_case", "case_id": None, "case_number": fields.get("case_number") or "",
            "case_name": fields.get("case_name") or "", "fields": fields,
            "changes": [{"field": k, "before": None, "after": v} for k, v in fields.items()]}


def _plan_update(data, lang):
    case = find_case(data.get("case"))
    if not case:
        raise Invalid(t(lang, "act_case_not_found", ref=data.get("case") or "—"))
    fields = clean_fields(data.get("fields") or {}, lang, case["id"])
    append = str(data.get("append_text") or "").strip()
    if len(append) > MAX_APPEND:
        raise Invalid(t(lang, "act_too_long", field=_label(lang, "case_text")))
    if append and "case_text" in fields:
        raise Invalid(t(lang, "act_append_and_replace"))
    changed = {k: v for k, v in fields.items() if not _same(case.get(k), v)}
    if not changed and not append:
        raise Invalid(t(lang, "act_no_change"))
    return {**_target(case), "type": "update_case", "fields": changed,
            "changes": [{"field": k, "before": case.get(k), "after": v} for k, v in changed.items()],
            "append_text": append or None}


def _plan_analyze(data, lang):
    case = find_case(data.get("case"))
    if not case:
        raise Invalid(t(lang, "act_case_not_found", ref=data.get("case") or "—"))
    if case.get("status") == "analyzing":
        raise Invalid(t(lang, "act_already_analyzing"))
    return {**_target(case), "type": "analyze_case", "fields": {}, "changes": []}


PLANS = {"create_case": _plan_create, "update_case": _plan_update, "analyze_case": _plan_analyze}


def propose(data, lang):
    """The action a reply's block asks for: pending when it can be applied, invalid with a reason if not."""
    kind = data.get("action") if isinstance(data, dict) else None
    try:
        if kind not in PLANS:
            raise Invalid(t(lang, "act_unknown"))
        action = PLANS[kind](data, lang)
    except Invalid as exc:
        return {"type": kind if kind in KINDS else "unknown", "status": "invalid", "error": str(exc),
                "fields": {}, "changes": []}
    action.update(status="pending", error=None)
    return action


def load(message):
    """The action stored on a message, as a dict, or None."""
    raw = (message or {}).get("action")
    if not raw:
        return None
    try:
        action = json.loads(raw)
    except ValueError:
        return None
    return action if isinstance(action, dict) else None


def _save(message_id, action):
    db.update_message(message_id, action=json.dumps(action, ensure_ascii=False))


def _locate_later(case_id, lang):
    # Like the case form, a new location is pinned on the map; the lookup can take seconds, so
    # the confirmation does not wait for it.
    threading.Thread(target=analysis.locate, args=(case_id, lang), daemon=True).start()


def _apply_create(action, lang):
    fields = clean_fields(action.get("fields") or {}, lang)
    if not fields.get("case_text"):
        raise Invalid(t(lang, "act_need_case_text"))
    case_id = db.create_draft(fields.pop("case_text"))
    fields["case_number"] = fields.get("case_number") or db.next_case_number()
    db.update_case(case_id, **fields)
    if fields.get("location"):
        _locate_later(case_id, lang)
    return db.get_case(case_id)


def _apply_update(action, lang):
    case = db.get_case(action.get("case_id"))
    if not case:
        raise Invalid(t(lang, "act_case_gone"))
    for change in action.get("changes") or []:
        if not _same(case.get(change["field"]), change.get("before")):
            raise Invalid(t(lang, "act_conflict", field=_label(lang, change["field"])))
    updates = clean_fields(action.get("fields") or {}, lang, case["id"])
    append = action.get("append_text")
    if append:
        updates["case_text"] = f"{(case.get('case_text') or '').rstrip()}\n\n{append}".strip()
    if "location" in updates:
        updates.update(latitude=None, longitude=None)
    db.update_case(case["id"], **updates)
    if updates.get("location"):
        _locate_later(case["id"], lang)
    return db.get_case(case["id"])


def _apply_analyze(action, lang):
    case = db.get_case(action.get("case_id"))
    if not case:
        raise Invalid(t(lang, "act_case_gone"))
    if case.get("status") == "analyzing":
        raise Invalid(t(lang, "act_already_analyzing"))
    analysis.start_analysis(case["id"], lang)
    return db.get_case(case["id"])


APPLY = {"create_case": _apply_create, "update_case": _apply_update, "analyze_case": _apply_analyze}


def confirm(message_id, lang):
    """Apply a pending action. Returns the action as it ends, or None when it was not pending."""
    if not db.claim_action(message_id, "pending", "applying"):
        return None
    action = load(db.get_message(message_id)) or {}
    try:
        case = APPLY[action.get("type")](action, lang)
    except Invalid as exc:
        action.update(status="failed", error=str(exc))
    except Exception as exc:  # the action must end failed, never stay "applying"
        log.exception("Action on message %s failed", message_id)
        action.update(status="failed", error=t(lang, "act_failed", err=exc))
    else:
        action.update(_target(case), status="confirmed", error=None)
    _save(message_id, action)
    return action


def cancel(message_id):
    """Cancel a pending action. False when it was not pending."""
    return db.claim_action(message_id, "pending", "cancelled")


def history_note(action):
    """One line telling the model what became of an action it proposed earlier."""
    if not action:
        return ""
    target = action.get("case_number") or (f"#{action['case_id']}" if action.get("case_id") else "")
    note = f"[Action {action.get('type')} {target}".rstrip() + f": {action.get('status')}"
    if action.get("error"):
        note += f" — {action['error']}"
    return note + "]"
