"""Provider settings: the numbered layout, and the older names from .env.example still working."""
import config

PROVIDER_VARS = [f"LLM_{i}_{field}" for i in range(1, config.MAX_PROVIDERS + 1)
                 for field in ("URL", "KEY", "MODEL", "VISION_MODEL", "LABEL")]
LEGACY_VARS = ["LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "VISION_MODEL", "BACKUP_LLM_BASE_URL",
               "BACKUP_LLM_API_KEY", "BACKUP_LLM_MODEL", "BACKUP_VISION_MODEL", "LLM_PROVIDERS"]


def _clean_env(monkeypatch):
    for name in PROVIDER_VARS + LEGACY_VARS:
        monkeypatch.delenv(name, raising=False)


def _providers():
    return [p for p in config._declared_providers() if p]


def test_env_example_layout_gives_one_provider(monkeypatch):
    """The README's three lines (LLM_API_KEY, LLM_BASE_URL, LLM_MODEL) are enough."""
    _clean_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example/v1/")
    monkeypatch.setenv("LLM_MODEL", "model-a")
    monkeypatch.setenv("VISION_MODEL", "vision-a")
    providers = _providers()
    assert [(p["index"], p["url"], p["model"], p["vision_model"]) for p in providers] == [
        ("1", "https://api.example/v1", "model-a", "vision-a")]


def test_backup_names_become_provider_two(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "k1")
    monkeypatch.setenv("BACKUP_LLM_BASE_URL", "https://backup/v1")
    monkeypatch.setenv("BACKUP_LLM_API_KEY", "k2")
    monkeypatch.setenv("BACKUP_LLM_MODEL", "backup-model")
    providers = _providers()
    assert [p["index"] for p in providers] == ["1", "2"]
    assert providers[1]["url"] == "https://backup/v1" and providers[1]["model"] == "backup-model"


def test_numbered_names_win_over_the_older_ones(monkeypatch):
    _clean_env(monkeypatch)
    monkeypatch.setenv("LLM_API_KEY", "old")
    monkeypatch.setenv("LLM_1_KEY", "new")
    monkeypatch.setenv("LLM_1_URL", "https://one/v1")
    monkeypatch.setenv("LLM_1_MODEL", "m1")
    monkeypatch.setenv("LLM_3_URL", "https://three/v1")
    monkeypatch.setenv("LLM_3_KEY", "k3")
    monkeypatch.setenv("LLM_3_MODEL", "m3")
    providers = _providers()
    assert [(p["index"], p["key"]) for p in providers] == [("1", "new"), ("3", "k3")]


def test_provider_list_sets_the_order(monkeypatch):
    _clean_env(monkeypatch)
    for i in ("1", "2"):
        monkeypatch.setenv(f"LLM_{i}_URL", f"https://p{i}/v1")
        monkeypatch.setenv(f"LLM_{i}_KEY", f"k{i}")
        monkeypatch.setenv(f"LLM_{i}_MODEL", f"m{i}")
    monkeypatch.setenv("LLM_PROVIDERS", "2,1")
    assert [p["index"] for p in _providers()] == ["2", "1"]


def test_no_key_means_no_provider(monkeypatch):
    _clean_env(monkeypatch)
    assert _providers() == []
