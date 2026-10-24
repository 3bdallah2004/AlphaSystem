"""Turning a location name into coordinates, and pinning a case on the map from its text."""
import pytest
import requests

import analysis
import geocode


@pytest.fixture(autouse=True)
def _lookups_on(monkeypatch):
    """conftest turns lookups off for the default suite; these tests turn them back on."""
    monkeypatch.setattr(geocode, "GEOCODE_ENABLED", True)
    monkeypatch.setattr(geocode, "MIN_INTERVAL", 0)     # no waiting between calls in tests
    yield


class FakeResponse:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload, self.status_code, self.text = payload, status_code, text
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


RAMALLAH = [{"lat": "31.8978012", "lon": "35.1924223", "importance": 0.6}]


def _patch(monkeypatch, response=None, exc=None):
    seen = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.update(url=url, params=params, headers=headers, timeout=timeout)
        if exc:
            raise exc
        return response

    monkeypatch.setattr(geocode.requests, "get", fake_get)
    return seen


# ── _clean ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("text,expected", [
    ("رام الله", "رام الله"),
    ("  رام الله  ", "رام الله"),
    ("الموقع: رام الله", "رام الله"),
    ("location: Ramallah", "Ramallah"),
    ("رام الله.", "رام الله"),
    ("مستودع رام الله المركزي", "مستودع رام الله المركزي"),
])
def test_clean_keeps_real_places(text, expected):
    assert geocode._clean(text) == expected


@pytest.mark.parametrize("text", [
    "", None, "   ", "غير محدد", "عبر الإنترنت", "عدة مدن", "not provided", "Unknown",
    "n/a", "online",
])
def test_clean_rejects_non_places(text):
    assert geocode._clean(text) == ""


def test_clean_rejects_a_whole_sentence():
    sentence = ("وقع الحادث في تمام الساعة الثالثة صباحاً أمام المستودع المركزي في مدينة رام الله")
    assert geocode._clean(sentence) == ""


def test_clean_rejects_absurdly_long_text():
    assert geocode._clean("ر" * 200) == ""


# ── find ─────────────────────────────────────────────────────────────────────
def test_find_returns_coordinates(monkeypatch):
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    assert geocode.find("رام الله") == (31.897801, 35.192422)
    assert seen["params"]["q"] == "رام الله"
    assert seen["params"]["format"] == "jsonv2"


def test_find_sends_a_named_user_agent(monkeypatch):
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    geocode.find("رام الله")
    assert "Alpha" in seen["headers"]["User-Agent"]


def test_find_asks_for_the_language(monkeypatch):
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    geocode.find("Ramallah", "en")
    assert seen["params"]["accept-language"] == "en"


def test_find_skips_non_places_without_any_request(monkeypatch):
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    assert geocode.find("عبر الإنترنت") is None
    assert seen == {}


def test_find_respects_the_enabled_switch(monkeypatch):
    monkeypatch.setattr(geocode, "GEOCODE_ENABLED", False)
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    assert geocode.find("رام الله") is None
    assert seen == {}


@pytest.mark.parametrize("response", [
    FakeResponse([]),                                  # nothing found
    FakeResponse(None, status_code=500),               # server error
    FakeResponse({"unexpected": "object"}),            # not a list
    FakeResponse([{"lat": "31.9"}]),                   # missing longitude
    FakeResponse([{"lat": "abc", "lon": "35.2"}]),     # unparseable
    FakeResponse([{"lat": "31.9", "lon": "35.2", "importance": 0.01}]),   # too unsure
    FakeResponse([{"lat": "999", "lon": "35.2", "importance": 0.9}]),     # out of range
    FakeResponse(None),                                # body is not JSON
])
def test_find_returns_none_for_unusable_answers(monkeypatch, response):
    _patch(monkeypatch, response)
    assert geocode.find("رام الله") is None


@pytest.mark.parametrize("exc", [
    requests.exceptions.ConnectionError("down"),
    requests.exceptions.Timeout(),
    requests.exceptions.RequestException("boom"),
])
def test_find_never_raises_on_network_errors(monkeypatch, exc):
    _patch(monkeypatch, exc=exc)
    assert geocode.find("رام الله") is None


def test_find_does_not_wait_between_calls_when_interval_is_zero(monkeypatch):
    _patch(monkeypatch, FakeResponse(RAMALLAH))
    for _ in range(3):
        assert geocode.find("رام الله") is not None


# ── analysis.locate ──────────────────────────────────────────────────────────
def test_locate_pins_a_case_without_one(database, case, monkeypatch):
    database.update_case(case, location="رام الله")
    monkeypatch.setattr(geocode, "find", lambda location, lang: (31.9, 35.2))
    assert analysis.locate(case, "ar") is True
    row = database.get_case(case)
    assert (row["latitude"], row["longitude"]) == (31.9, 35.2)


def test_locate_leaves_a_hand_placed_pin_alone(database, case, monkeypatch):
    database.update_case(case, location="رام الله", latitude=32.0, longitude=35.0)
    called = []
    monkeypatch.setattr(geocode, "find", lambda *a: called.append(1) or (31.9, 35.2))
    assert analysis.locate(case, "ar") is False
    assert called == []
    assert database.get_case(case)["latitude"] == 32.0


def test_locate_does_nothing_when_the_lookup_fails(database, case, monkeypatch):
    database.update_case(case, location="عبر الإنترنت")
    monkeypatch.setattr(geocode, "find", lambda *a: None)
    assert analysis.locate(case, "ar") is False
    assert database.get_case(case)["latitude"] is None


def test_locate_survives_a_missing_case(database, monkeypatch):
    monkeypatch.setattr(geocode, "find", lambda *a: (31.9, 35.2))
    assert analysis.locate(424242, "ar") is False


# ── region bias ──────────────────────────────────────────────────────────────
def test_lookup_carries_the_region_bounds(monkeypatch):
    """Without it, "Jenin" resolves to a village in Poland instead of the West Bank city."""
    seen = _patch(monkeypatch, FakeResponse(RAMALLAH))
    geocode.find("Jenin", "en")
    assert seen["params"]["viewbox"] == "34.2,33.4,35.9,31.2"
    assert seen["params"]["bounded"] == 0          # a hint, not a restriction


def test_region_bounds_parse_in_corner_order():
    (north, west), (south, east) = geocode.REGION_BOUNDS
    assert (north, west) == (33.4, 34.2)
    assert (south, east) == (31.2, 35.9)
    # The map's own default centre sits inside the box.
    lat, lng = 31.95, 35.25
    assert south <= lat <= north and west <= lng <= east


def test_no_bounds_means_no_viewbox_params():
    import geocode as g

    saved = g.REGION_BOUNDS
    try:
        g.REGION_BOUNDS = None
        assert g._region_params() == {}
    finally:
        g.REGION_BOUNDS = saved
