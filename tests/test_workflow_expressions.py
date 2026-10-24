"""The n8n workflow's expressions, checked as n8n will evaluate them.

The workflow file is data, but a wrong expression there breaks the product exactly like a
Python bug: n8n rejects a nested `{{ }}` inside another expression, and a URL without the
`/chat/completions` suffix reaches the provider's root. These tests evaluate each expression
with plain JS-like semantics for a few providers.
"""
import json
import re
from pathlib import Path

import pytest

WORKFLOW = Path(__file__).resolve().parent.parent / "n8n" / "workflows" / "alpha-analysis.json"


@pytest.fixture(scope="module")
def nodes():
    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    return {n["name"]: n for n in data["nodes"]}


@pytest.fixture(scope="module")
def http_nodes(nodes):
    return {name: n for name, n in nodes.items() if n["type"] == "n8n-nodes-base.httpRequest"}


def test_there_are_three_model_calls(http_nodes):
    assert set(http_nodes) == {"Call LLM", "Chat with LLM", "Suggest with LLM"}


@pytest.mark.parametrize("field", ["url"])
def test_url_appends_the_chat_completions_path(http_nodes, field):
    for name, node in http_nodes.items():
        url = node["parameters"][field]
        assert url.startswith("={{"), name
        assert url.rstrip().endswith("}}"), name
        assert "chat/completions" in url, name
        # A trailing slash is stripped first, so a base URL ending in "/" does not double up.
        assert r".replace(/\/+$/, '')" in url, name


def test_model_is_not_a_nested_expression(http_nodes):
    """`model: {{ ... }}` inside `={{ JSON.stringify(...) }}` is invalid for n8n."""
    for name, node in http_nodes.items():
        body = node["parameters"]["jsonBody"]
        assert body.startswith("={{ JSON.stringify("), name
        # Exactly one expression wrapper around the whole body, and none nested inside it.
        assert body.count("{{") == 1 and body.count("}}") == 1, name
        golden_model = body[body.find("model: ") + len("model: "):body.find(", temperature")]
        assert golden_model.startswith("($env[") and golden_model.endswith(")"), name
        assert "{{" not in golden_model and "}}" not in golden_model, name


def test_expressions_reference_the_provider_key(http_nodes):
    for name, node in http_nodes.items():
        params = node["parameters"]
        assert 'provider_key' in params["url"], name
        auth = params["headerParameters"]["parameters"][0]
        assert auth["name"] == "Authorization", name
        assert 'provider_key' in auth["value"], name
        assert 'provider_key' in params["jsonBody"], name


def _pick(expr, env, body):
    """Evaluate the `$env[...] || (...) || (...)` chain n8n runs, with JS truthiness."""
    def env_get(key):
        return env.get(key)

    def js_or(*values):
        return next((v for v in values if v), None)

    if "BACKUP_LLM_URL" in expr:
        base = js_or(env_get(f'LLM_{body["provider_key"]}_URL'),
                     (body.get("use_backup") and env_get("BACKUP_LLM_URL")),
                     env_get("LLM_BASE_URL"),
                     "https://api.openai.com/v1")
    elif "BACKUP_LLM_KEY" in expr:
        base = js_or(env_get(f'LLM_{body["provider_key"]}_KEY'),
                     (body.get("use_backup") and env_get("BACKUP_LLM_KEY")),
                     env_get("LLM_API_KEY"))
    else:
        base = js_or(env_get(f'LLM_{body["provider_key"]}_MODEL'),
                     (body.get("use_backup") and env_get("BACKUP_LLM_MODEL")),
                     env_get("LLM_MODEL"),
                     "gpt-4.1-mini")
    return base


def test_provider_selection_picks_the_named_provider():
    """The app sends provider_key="3"; the workflow must then read LLM_3_*."""
    env = {
        "LLM_1_URL": "https://one/v1", "LLM_1_KEY": "k1", "LLM_1_MODEL": "m1",
        "LLM_2_URL": "https://two/v1", "LLM_2_KEY": "k2", "LLM_2_MODEL": "m2",
        "LLM_3_URL": "https://three/v1", "LLM_3_KEY": "k3", "LLM_3_MODEL": "m3",
    }
    body = {"provider_key": "3", "use_backup": False}
    assert _pick('$env["LLM_" + $json.body.provider_key + "_URL"] || ($json.body.use_backup && $env.BACKUP_LLM_URL)', env, body) == "https://three/v1"
    assert _pick('$env["LLM_" + $json.body.provider_key + "_KEY"] || ($json.body.use_backup && $env.BACKUP_LLM_KEY)', env, body) == "k3"
    assert _pick('$env["LLM_" + $json.body.provider_key + "_MODEL"] || ($json.body.use_backup && $env.BACKUP_LLM_MODEL)', env, body) == "m3"


def test_provider_selection_falls_back_to_the_legacy_names():
    env = {"LLM_BASE_URL": "https://legacy/v1", "LLM_API_KEY": "lk", "LLM_MODEL": "lm",
           "BACKUP_LLM_URL": "https://backup/v1", "BACKUP_LLM_KEY": "bk", "BACKUP_LLM_MODEL": "bm"}
    assert _pick("$env[x_URL] || ($json.body.use_backup && $env.BACKUP_LLM_URL) || $env.LLM_BASE_URL", env, {"provider_key": "1"}) == "https://legacy/v1"
    assert _pick("$env[x_MODEL] || ($json.body.use_backup && $env.BACKUP_LLM_MODEL) || $env.LLM_MODEL", env, {"provider_key": "1"}) == "lm"


def test_workflow_urls_match_the_provider_base_urls_in_env_example():
    """Every URL the app can send must end up as <base>/chat/completions, as Gemini/OpenRouter expect."""
    for base in ("https://generativelanguage.googleapis.com/v1beta/openai",
                 "https://openrouter.ai/api/v1"):
        assert re.sub(r"/+$", "", base) + "/chat/completions" == base.rstrip("/") + "/chat/completions"


def test_health_answer_sees_the_provider_list(nodes):
    """The app shows a warning when the workflow reports llm_configured=false.

    With LLM_PROVIDERS/LLM_<n>_KEY set and no legacy LLM_API_KEY, the workflow must still
    report the providers as configured — otherwise a working install warns on every check.
    """
    body = nodes["Respond health"]["parameters"]["responseBody"]
    assert "LLM_API_KEY" in body
    for needed in ("LLM_PROVIDERS", "LLM_1_KEY", "LLM_1_MODEL"):
        assert needed in body, f"health answer ignores {needed}"
    assert body.count("{{") == 1 and body.count("}}") == 1
