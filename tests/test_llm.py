"""Provider rotation, quota detection, and the text helpers."""
import llm
import pytest


@pytest.fixture(autouse=True)
def _clean():
    llm.clear_exhausted()
    yield
    llm.clear_exhausted()


# ── looks_like_quota ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("code,body,expected", [
    (429, "", True),
    (200, "quota exceeded", True),
    (400, "RESOURCE_EXHAUSTED", True),
    (503, "Try spacing your requests out", True),
    (400, "invalid api key", False),
    (500, "internal error", False),
    (200, None, False),
])
def test_looks_like_quota(code, body, expected):
    assert llm.looks_like_quota(code, body) is expected


# ── candidates ───────────────────────────────────────────────────────────────
def test_candidates_lists_configured_providers():
    assert [p["index"] for p in llm.candidates("text")] == ["1"]


def test_candidates_skip_vision_when_disabled(monkeypatch):
    monkeypatch.setattr(llm, "VISION_ENABLED", False)
    assert llm.candidates("vision") == []


def test_candidates_put_spent_provider_last(monkeypatch):
    second = {"index": "2", "id": "2:http://x", "name": "p2", "url": "http://x",
              "key": "k", "model": "m2", "vision_model": "m2"}
    monkeypatch.setattr(llm, "PROVIDERS", llm.PROVIDERS + [second])
    llm.set_aside(second["index"])
    assert [p["index"] for p in llm.candidates("text")] == ["1", "2"]
    # Every provider spent: all are still offered, so the request can succeed once a quota resets.
    llm.set_aside(llm.PROVIDERS[0]["index"])
    assert sorted(p["index"] for p in llm.candidates("text")) == ["1", "2"]


def test_candidates_ignores_incomplete_provider(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [dict(llm.PROVIDERS[0], key="")])
    assert llm.candidates("text") == []


def test_model_for_picks_vision_model():
    provider = llm.PROVIDERS[0]
    assert llm.model_for(provider, "text") == "test-model"
    assert llm.model_for(provider, "vision") == "test-vision"


# ── set_aside / recovery ─────────────────────────────────────────────────────
def test_set_aside_by_index_and_by_id():
    provider = llm.PROVIDERS[0]
    assert llm.set_aside(provider["index"])["id"] == provider["id"]
    assert llm._is_set_aside(provider["id"])
    llm.clear_exhausted()
    assert llm.set_aside(provider["id"])["id"] == provider["id"]
    assert llm._is_set_aside(provider["id"])


def test_set_aside_unknown_index_returns_none():
    assert llm.set_aside("99") is None


def test_cooldown_expires(monkeypatch):
    provider = llm.PROVIDERS[0]
    llm._set_aside(provider["id"])
    assert llm._is_set_aside(provider["id"])
    monkeypatch.setattr(llm.time, "time", lambda: 10 ** 12)
    assert not llm._is_set_aside(provider["id"])
    assert llm._recover_in(provider["id"]) == 0


def test_vision_provider_comes_first_for_images(monkeypatch):
    vision_only = {"index": "vision", "id": "vision:http://v", "name": "vision", "url": "http://v",
                   "key": "vk", "model": "vm", "vision_model": "vm"}
    monkeypatch.setattr(llm, "VISION_PROVIDER", vision_only)
    assert [p["index"] for p in llm.candidates("vision")] == ["vision", "1"]
    # Text requests never go to the dedicated vision provider.
    assert [p["index"] for p in llm.candidates("text")] == ["1"]


def test_status_reports_state():
    state = llm.status()
    assert state["count"] == 1
    assert state["main_model"] == "test-model"
    assert state["backup_ready"] is False
    assert state["providers"][0]["index"] == "1"


def test_clear_exhausted_resets_switch_note():
    llm.clear_exhausted()
    assert llm.status()["providers"][0]["set_aside_s"] == 0


# ── chat_completions ─────────────────────────────────────────────────────────
class FakeResponse:
    def __init__(self, payload=None, text="", status_code=200):
        self._payload, self.text, self.status_code = payload, text, status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError
        return self._payload


def test_chat_completions_returns_response(monkeypatch):
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        return FakeResponse({"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(llm.requests, "post", fake_post)
    response, error = llm.chat_completions("text", {"messages": []})
    assert error is None
    assert sent["url"].endswith("/chat/completions")
    assert sent["body"]["model"] == "test-model"
    assert sent["headers"]["Authorization"] == "Bearer test-key"


def test_chat_completions_hard_error_is_returned(monkeypatch):
    monkeypatch.setattr(llm.requests, "post", lambda *a, **kw: FakeResponse({"error": "bad"}, "", 400))
    response, error = llm.chat_completions("text", {})
    assert error is None and response.status_code == 400


def test_chat_completions_timeout_reports_reason(monkeypatch):
    import requests

    def boom(*a, **kw):
        raise requests.exceptions.Timeout()

    monkeypatch.setattr(llm.requests, "post", boom)
    response, error = llm.chat_completions("text", {})
    assert response is None and "timed out" in error


def test_chat_completions_no_provider(monkeypatch):
    monkeypatch.setattr(llm, "PROVIDERS", [])
    response, error = llm.chat_completions("text", {})
    assert response is None and "no provider" in error
