"""Choosing which model provider answers a request.

Any number of OpenAI-compatible providers can be configured (see config.PROVIDERS). Each has
its own free quota, and each is tracked separately: when one reports a spent quota it is set
aside and the next provider is used. When every provider has been set aside, the one that
recovers soonest is tried again, so a day of limits does not stop the work.
"""
import os
import threading
import time

import http_pool as requests

from config import PROVIDERS, PROVIDER_TIMEOUT, VISION_ENABLED, VISION_PROVIDER

# How long a provider is set aside after it reports a spent quota. Kept well under a day so
# the providers keep rotating within a working session.
COOLDOWN = int(os.getenv("ALPHA_PROVIDER_COOLDOWN") or 30 * 60)

# Wording the providers use when a quota or rate limit is hit. OpenRouter's own daily-limit
# message does not always contain "rate limit": it may arrive as only the generic
# "Try spacing your requests out" hint, so that phrase is matched too.
QUOTA_MARKERS = (
    "free-models-per-day", "rate limit", "ratelimit", "quota", "resource_exhausted",
    "too many requests", "spacing your requests", "x-ratelimit",
)

_lock = threading.Lock()
_set_aside_at = {}     # provider id -> time it may be tried again
_last_switch = None    # (time, description) of the most recent switch, for the UI


def looks_like_quota(status_code, body):
    """A spent quota rather than a bad request."""
    if status_code == 429:
        return True
    text = (body or "").lower()
    return any(marker in text for marker in QUOTA_MARKERS)


def _set_aside(provider_id):
    with _lock:
        _set_aside_at[provider_id] = time.time() + COOLDOWN


def _is_set_aside(provider_id):
    with _lock:
        return time.time() < _set_aside_at.get(provider_id, 0)


def _recover_in(provider_id):
    with _lock:
        return max(0, int(_set_aside_at.get(provider_id, 0) - time.time()))


def _record_switch(description):
    global _last_switch
    with _lock:
        _last_switch = (time.time(), description)


def clear_exhausted():
    """Forget every cooldown, e.g. after a key is changed."""
    with _lock:
        _set_aside_at.clear()


def set_aside(index_or_id):
    """Set aside one provider, by its index in PROVIDERS or by its id."""
    for provider in PROVIDERS + ([VISION_PROVIDER] if VISION_PROVIDER else []):
        if provider["index"] == str(index_or_id) or provider["id"] == index_or_id:
            _set_aside(provider["id"])
            _record_switch(f'{provider["model"]} out of quota')
            return provider
    return None


def candidates(role):
    """Providers to try for this role, best first.

    A provider whose quota is spent goes last, so the others are used first; when all are
    spent the one that recovers soonest is still tried, in case its quota already reset.
    For images, a dedicated vision provider (VISION_BASE_URL / VISION_API_KEY) comes first.
    """
    if role == "vision" and not VISION_ENABLED:
        return []
    pool = list(PROVIDERS)
    if role == "vision" and VISION_PROVIDER:
        pool.insert(0, VISION_PROVIDER)
    usable = []
    for order, provider in enumerate(pool):
        if not provider.get("key") or not provider.get("model"):
            continue
        usable.append((_is_set_aside(provider["id"]), _recover_in(provider["id"]), order, provider))
    usable.sort(key=lambda item: item[:3])
    return [item[3] for item in usable]


def model_for(provider, role):
    return provider["vision_model"] if role == "vision" else provider["model"]


def status():
    """What the UI needs to explain which provider is in use."""
    first = PROVIDERS[0] if PROVIDERS else {}
    second = PROVIDERS[1] if len(PROVIDERS) > 1 else {}
    return {
        "count": len(PROVIDERS),
        "main_model": first.get("model"),
        "backup_model": second.get("model"),
        "backup_ready": len(PROVIDERS) > 1,
        "main_set_aside_s": _recover_in(first["id"]) if first else 0,
        "backup_set_aside_s": _recover_in(second["id"]) if second else 0,
        "providers": [{"index": p["index"], "model": p["model"],
                       "set_aside_s": _recover_in(p["id"])} for p in PROVIDERS],
        "switched_at": _last_switch,
    }


def chat_completions(role, payload, timeout=None):
    """Send an OpenAI-style chat request, moving to the next provider when a quota is spent.

    Returns (response, error_message): the last response received, or None with a reason when
    no provider could be reached at all.
    """
    tried = []
    options = candidates(role)
    for index, provider in enumerate(options):
        body = dict(payload, model=model_for(provider, role))
        url = f'{provider["url"]}/chat/completions'
        wait = timeout or PROVIDER_TIMEOUT
        try:
            response = requests.post(url, json=body,
                                     headers={"Authorization": f'Bearer {provider["key"]}'},
                                     timeout=(10, wait))
        except requests.exceptions.Timeout:
            tried.append(f'{provider["model"]}: timed out')
            continue
        except requests.exceptions.RequestException as exc:
            tried.append(f'{provider["model"]}: {exc}')
            continue

        if response.ok:
            if index > 0:
                _record_switch(f'{provider["model"]} answered instead')
            return response, None

        if looks_like_quota(response.status_code, response.text[:2000]):
            # This provider is spent: set it aside and try the next one.
            _set_aside(provider["id"])
            _record_switch(f'{provider["model"]} out of quota')
            tried.append(f'{provider["model"]}: quota spent')
            continue
        # Any other error would fail the same way elsewhere.
        return response, None

    return None, "; ".join(tried) or "no provider is configured"
