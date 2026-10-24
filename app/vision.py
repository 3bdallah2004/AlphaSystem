"""Describe case images and video frames with a vision model.

The analysis model (LLM_MODEL) may be text-only, so attachment images never reach it.
Instead this module turns them into text that joins the report before analysis.
"""
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import db
import llm
from config import (VISION_ENABLED, VISION_MAX_TOKENS, VISION_MODEL, VISION_RETRY_MAX_TOKENS,
                    VISION_TIMEOUT)
from i18n import t

PROMPT = (
    "You are assisting a criminal investigation. Describe this image as evidence, factually and "
    "concretely: what is shown, people (without guessing identities), objects, vehicles, visible text "
    "verbatim, injuries or damage, time-of-day and setting cues, and anything that could be evidence. "
    "State clearly when something is unclear or unreadable. Do not speculate beyond what is visible. "
    "Answer in LANGUAGE in at most 120 words."
)
VIDEO_CACHE_PREFIX = "[video-frames-v1]\n"


def enabled():
    """A vision model is usable when a provider is configured for it."""
    return bool(VISION_ENABLED and llm.candidates("vision"))


def _ask(lang, data_uri, max_tokens, timeout):
    """One vision call. Returns (text, finish_reason, error).

    error is the message to show when nothing usable came back, or None.
    """
    payload = {
        "max_tokens": max_tokens,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT.replace("LANGUAGE", "English" if lang == "en" else "Arabic")},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ],
        }],
    }
    r, error = llm.chat_completions("vision", payload, timeout=timeout or VISION_TIMEOUT)
    if r is None:
        return None, None, t(lang, "vis_http", code="—", detail=error or "")
    if not 200 <= r.status_code < 300:
        return None, None, t(lang, "vis_http", code=r.status_code, detail=_detail(r))
    try:
        choice = r.json()["choices"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        return None, None, t(lang, "vis_empty")
    text = ((choice.get("message") or {}).get("content") or "").strip()
    return text or None, choice.get("finish_reason"), None


def describe_image(lang, data_uri, timeout=None):
    """One factual description of one image. Returns (text, None) or (None, error_message).

    Uses the backup provider when the main one has run out of quota. A reasoning model can
    spend a whole token budget thinking and return nothing with finish_reason "length" (seen
    on OpenRouter free vision models); that one case is retried with a larger budget instead
    of being reported as an unreadable image.
    """
    if not enabled():
        return None, t(lang, "vis_not_configured")
    text, finish, error = _ask(lang, data_uri, VISION_MAX_TOKENS, timeout)
    if text:
        return text, None
    if error:
        return None, error
    truncated = finish == "length"
    text, finish, error = _ask(lang, data_uri, VISION_RETRY_MAX_TOKENS, timeout)
    if text:
        return text, None
    if error:
        return None, error
    return None, t(lang, "vis_truncated" if (truncated or finish == "length") else "vis_empty")


def describe_many(lang, items, timeout=None, cache=None):
    """[(label, data_uri, attachment_id)] -> (description_text, [errors]).

    Images are described in parallel: a reasoning vision model takes about a minute each,
    and a case can carry several. Descriptions are cached per attachment, so re-analysis
    reuses them instead of paying that cost again.
    """
    if not items:
        return "", []
    parts, errors = [None] * len(items), []
    descriptions, failed_video_caches = {}, set()
    pending = []
    for index, item in enumerate(items):
        label, _, att_id = item[:3]
        cacheable = item[3] if len(item) > 3 else True
        cached = cache.get(att_id) if cache and cacheable else None
        if cacheable == "video" and cached and not cached.startswith(VIDEO_CACHE_PREFIX):
            cached = None
        if cached:
            if cacheable == "video":
                cached = cached[len(VIDEO_CACHE_PREFIX):]
            parts[index] = f"[{label}]\n{cached}"
        else:
            pending.append((index, item, cacheable))

    if not pending:
        return "\n\n".join(p for p in parts if p), errors

    with ThreadPoolExecutor(max_workers=min(4, len(pending))) as pool:
        futures = {pool.submit(describe_image, lang, item[1], timeout): (index, item, cacheable)
                   for index, item, cacheable in pending}
        for future in as_completed(futures):
            index, item, cacheable = futures[future]
            label, _, att_id = item[:3]
            try:
                text, error = future.result()
            except Exception as exc:  # a provider hiccup must not sink the whole analysis
                text, error = None, str(exc)
            if text:
                parts[index] = f"[{label}]\n{text}"
                if att_id and cacheable:
                    value = f"[{label}]\n{text}" if cacheable == "video" else text
                    descriptions.setdefault(att_id, []).append((index, value, cacheable))
            elif error:
                errors.append(f"{label}: {error}")
                if att_id and cacheable == "video":
                    failed_video_caches.add(att_id)
    for att_id, chunks in descriptions.items():
        if att_id in failed_video_caches:
            continue
        chunks.sort(key=lambda chunk: chunk[0])
        mode = chunks[0][2]
        value = "\n\n".join(chunk[1] for chunk in chunks)
        if mode == "video":
            value = VIDEO_CACHE_PREFIX + value
        db.set_attachment_description(att_id, value, VISION_MODEL)
    return "\n\n".join(p for p in parts if p), errors


def _detail(response):
    try:
        data = response.json()
    except ValueError:
        return (response.text or "")[:300]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or json.dumps(error, ensure_ascii=False))[:300]
        if error:
            return str(error)[:300]
    return json.dumps(data, ensure_ascii=False)[:300]
