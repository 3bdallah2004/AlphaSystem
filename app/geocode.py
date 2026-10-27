"""Turn a case's location text into map coordinates.

The analyst writes (or the analysis suggests) a place name such as "رام الله" or
"مستودع رام الله". This module asks OpenStreetMap's Nominatim for its coordinates, so the case
appears on the map without anyone clicking it.

Only the cleaned place name leaves the server — never the report text. Nothing here raises:
a location is a convenience, and a lookup failure must not stop a case from being saved.
"""
import re
import threading
import time

import requests

from config import (GEOCODE_BOUNDS, GEOCODE_ENABLED, GEOCODE_MIN_IMPORTANCE, GEOCODE_TIMEOUT,
                    GEOCODE_URL)

# Nominatim ranks by its own importance, which ignores the map this app works on: "Jenin" first
# matched a village in Poland. The same search with the West Bank's bounding box puts the real
# Jenin first, so every lookup carries that box. Cases outside it still resolve, just lower.
REGION_BOUNDS = [(float(lat), float(lng)) for lat, lng in
                 (pair.split(",") for pair in GEOCODE_BOUNDS.split(";") if pair.strip())] or None

# Nominatim's usage policy asks for one request per second and a User-Agent that names the app.
MIN_INTERVAL = 1.0
USER_AGENT = "Alpha-Investigation-System/1.0 (case analysis app)"

# Words that mean "no place" rather than a place, in both languages the app speaks.
NOT_A_PLACE = (
    "غير محدد", "غير معروف", "غير متوفر", "لا يوجد", "بدون",
    "عبر الإنترنت", "الإنترنت", "اونلاين", "أونلاين", "عدة مدن", "مدن متعددة", "عدة مواقع",
    "غير قابل للتحديد", "مجهول",
    "not provided", "not specified", "unknown", "none", "n/a", "online", "the internet",
    "several cities", "multiple locations", "various locations",
)

# Leading noise a suggested or hand-typed location often carries.
_LEADING = re.compile(
    r"^(?:الموقع|المكان|مكان الحادثة|موقع الحادثة|العنوان|location|place|address)\s*[:\-–]\s*",
    re.I,
)


def _clean(location):
    """The place name to look up, or "" when the text is not a place at all."""
    text = (location or "").strip()
    text = _LEADING.sub("", text)
    text = re.sub(r"\s+", " ", text).strip(" .,;:-–—/")
    if not text or len(text) > 120:
        return ""
    lowered = text.lower()
    if any(phrase in lowered for phrase in NOT_A_PLACE):
        return ""
    # A whole sentence is not an address: lookups on it waste a request and return junk.
    if len(text.split()) > 8:
        return ""
    return text


_last_call = 0.0
_lock = threading.Lock()

# Answers already received, misses included, so the same place is never asked for twice in one
# run: Nominatim's policy forbids repeating a query, and a miss would otherwise be retried on
# every page that shows the case.
_cache = {}
_cache_lock = threading.Lock()
CACHE_LIMIT = 2000


def clear_cache():
    with _cache_lock:
        _cache.clear()


def _wait_for_turn():
    """Keep at most one request per second across threads."""
    global _last_call
    with _lock:
        pause = MIN_INTERVAL - (time.time() - _last_call)
        if pause > 0:
            time.sleep(pause)
        _last_call = time.time()


def _region_params():
    """Nominatim viewbox: left,top,right,bottom, with results inside it preferred."""
    if not REGION_BOUNDS:
        return {}
    (north, west), (south, east) = REGION_BOUNDS
    return {"viewbox": f"{west},{north},{east},{south}", "bounded": 0}


def find(location, lang="ar"):
    """(lat, lng) for a place name, or None when it cannot be found confidently.

    Never raises.
    """
    if not GEOCODE_ENABLED:
        return None
    query = _clean(location)
    if not query:
        return None
    cache_key = (query.lower(), "en" if lang == "en" else "ar")
    with _cache_lock:
        if cache_key in _cache:
            return _cache[cache_key]
    point, definitive = _lookup(query, lang)
    if definitive:
        with _cache_lock:
            if len(_cache) >= CACHE_LIMIT:
                _cache.clear()
            _cache[cache_key] = point
    return point


def _lookup(query, lang):
    """(point_or_None, definitive). A network failure is not definitive, so it may be retried."""
    try:
        _wait_for_turn()
        response = requests.get(
            GEOCODE_URL,
            params=dict({"q": query, "format": "jsonv2", "limit": 3, "addressdetails": 0,
                         "accept-language": "en" if lang == "en" else "ar"},
                        **_region_params()),
            headers={"User-Agent": USER_AGENT},
            timeout=(4, GEOCODE_TIMEOUT),
        )
        if not response.ok:
            # 429 / 5xx are temporary; only a clean answer is worth remembering.
            return None, False
        results = response.json()
    except (requests.exceptions.RequestException, ValueError):
        return None, False
    if not isinstance(results, list) or not results:
        return None, True
    best = results[0]
    if not isinstance(best, dict):
        return None, True
    try:
        importance = float(best.get("importance") or 0)
        lat = float(best["lat"])
        lng = float(best["lon"])
    except (TypeError, ValueError, KeyError):
        return None, True
    if importance < GEOCODE_MIN_IMPORTANCE:
        return None, True
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, True
    return (round(lat, 6), round(lng, 6)), True
