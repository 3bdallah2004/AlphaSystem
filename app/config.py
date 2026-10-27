import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

try:
    from dotenv import load_dotenv

    # Real environment variables (e.g. from docker compose) always win over .env.
    load_dotenv(ROOT_DIR / ".env", override=False)
except ImportError:
    pass


def _default_db_path():
    # Older versions kept the database next to app.py; keep using it if it exists.
    legacy = ROOT_DIR / "alpha_database.db"
    if legacy.exists():
        return str(legacy)
    return str(ROOT_DIR / "data" / "alpha_database.db")


WEBHOOK_URL = os.getenv("ALPHA_WEBHOOK_URL") or "http://localhost:5678/webhook/alpha-analyze"
# Shared secret the workflow checks on every call (header X-Alpha-Token). Empty disables the check.
WEBHOOK_TOKEN = (os.getenv("ALPHA_WEBHOOK_TOKEN") or "").strip()
DB_PATH = os.getenv("ALPHA_DB_PATH") or _default_db_path()
REQUEST_TIMEOUT = int(os.getenv("ALPHA_REQUEST_TIMEOUT") or 120)
ALPHA_WORKER = (os.getenv("ALPHA_WORKER") or "api").strip() or "api"

# ── Model providers ───────────────────────────────────────────────────────────
# Any number of OpenAI-compatible providers can be configured, tried in order. When one
# reports a spent quota it is set aside and the next is used, so a free daily limit on any
# single provider does not stop work. Two ways to declare them:
#
#   LLM_PROVIDERS=1,2,3          which numbers exist, in the order to try them
#   LLM_1_URL / LLM_1_KEY / LLM_1_MODEL / LLM_1_VISION_MODEL
#   LLM_2_URL / ...              the next provider, and so on
#
# The older names still work and fill in whatever the numbered ones leave empty:
# LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / VISION_MODEL are provider 1, and
# BACKUP_LLM_BASE_URL / BACKUP_LLM_API_KEY / BACKUP_LLM_MODEL / BACKUP_VISION_MODEL are
# provider 2. docker-compose.yml applies the same fallbacks, so n8n sees the same providers.
VISION_TIMEOUT = int(os.getenv("ALPHA_VISION_TIMEOUT") or 90)
# A reasoning vision model spends part of the budget thinking before it writes. When it spends
# all of it and returns nothing, vision.describe_image retries with the larger budget.
VISION_MAX_TOKENS = int(os.getenv("ALPHA_VISION_MAX_TOKENS") or 1200)
VISION_RETRY_MAX_TOKENS = int(os.getenv("ALPHA_VISION_RETRY_MAX_TOKENS") or 3000)
VISION_ENABLED = (os.getenv("ALPHA_VISION_ENABLED") or "1").strip().lower() not in ("0", "false", "no", "off")
PROVIDER_TIMEOUT = int(os.getenv("ALPHA_PROVIDER_TIMEOUT") or 120)
AUDIO_TRANSCRIPTION_MODEL = os.getenv("ALPHA_AUDIO_TRANSCRIPTION_MODEL") or "whisper-1"


def _provider(index, url, key, model, vision_model="", label=""):
    """One provider entry, or None when it is not fully configured.

    Two providers can share a base URL (two keys for the same service), so `id` is what
    identifies a provider everywhere else: its key and URL together.
    """
    if not (url and key and model):
        return None
    url = url.rstrip("/")
    return {
        "index": index,
        "id": f"{index}:{url}",
        "name": label or f"provider {index}",
        "url": url,
        "key": key,
        "model": model,
        "vision_model": vision_model or model,
    }


# The older variable names behind each numbered field, with their defaults.
LEGACY_NAMES = {
    "1": {"URL": ("LLM_BASE_URL", "https://api.openai.com/v1"), "KEY": ("LLM_API_KEY", ""),
          "MODEL": ("LLM_MODEL", "gpt-4.1-mini"), "VISION_MODEL": ("VISION_MODEL", "")},
    "2": {"URL": ("BACKUP_LLM_BASE_URL", ""), "KEY": ("BACKUP_LLM_API_KEY", ""),
          "MODEL": ("BACKUP_LLM_MODEL", ""), "VISION_MODEL": ("BACKUP_VISION_MODEL", "")},
}
MAX_PROVIDERS = 9


def _setting(index, field):
    """LLM_<index>_<field>, falling back to its older name and default."""
    value = (os.getenv(f"LLM_{index}_{field}") or "").strip()
    if value:
        return value
    legacy, default = LEGACY_NAMES.get(str(index), {}).get(field, ("", ""))
    return ((os.getenv(legacy) or "").strip() if legacy else "") or default


def _declared_providers():
    """Providers in the order they should be tried."""
    listed = (os.getenv("LLM_PROVIDERS") or "").strip()
    if listed:
        indexes = [part.strip() for part in listed.split(",") if part.strip()]
    else:
        indexes = [str(i) for i in range(1, MAX_PROVIDERS + 1)]
    return [_provider(i, _setting(i, "URL"), _setting(i, "KEY"), _setting(i, "MODEL"),
                      _setting(i, "VISION_MODEL"), label=os.getenv(f"LLM_{i}_LABEL") or "")
            for i in indexes]


PROVIDERS = [p for p in _declared_providers() if p]

# The model named on image descriptions: the main provider's vision model.
VISION_MODEL = PROVIDERS[0]["vision_model"] if PROVIDERS else ""

# A dedicated vision provider (VISION_BASE_URL / VISION_API_KEY) is tried before the others for
# images, so a text-only analysis provider can be paired with a provider that reads images.
_vision_key = (os.getenv("VISION_API_KEY") or "").strip()
_vision_url = (os.getenv("VISION_BASE_URL") or "").strip()
VISION_PROVIDER = None
if _vision_key or _vision_url:
    _main = PROVIDERS[0] if PROVIDERS else {}
    VISION_PROVIDER = _provider("vision", _vision_url or _main.get("url"), _vision_key or _main.get("key"),
                                (os.getenv("VISION_MODEL") or "").strip() or _main.get("vision_model"),
                                label="vision")
    if VISION_PROVIDER:
        VISION_MODEL = VISION_PROVIDER["vision_model"]

# Attachments sit next to the database, inside the same volume, so both survive a rebuild.
ATTACHMENTS_DIR = os.getenv("ALPHA_ATTACHMENTS_DIR") or str(Path(DB_PATH).parent / "attachments")

# ── Automatic place lookup ────────────────────────────────────────────────────
# A case's location text (written by the analyst or suggested from the report) is turned into
# map coordinates with OpenStreetMap's Nominatim. Only the place name is sent there, never the
# report text. Its usage policy allows one request per second, which geocode.py enforces.
GEOCODE_ENABLED = (os.getenv("ALPHA_GEOCODE_ENABLED") or "1").strip().lower() not in ("0", "false", "no", "off")
GEOCODE_URL = os.getenv("ALPHA_GEOCODE_URL") or "https://nominatim.openstreetmap.org/search"
GEOCODE_TIMEOUT = int(os.getenv("ALPHA_GEOCODE_TIMEOUT") or 8)
# Sampled from the app's default map view: the region its causes happen in. It only biases the
# search — "Jenin" as a West Bank city instead of a village in Poland — never excludes an answer.
# Format: "north,west;south,east" (the corners of the region); empty disables the bias.
GEOCODE_BOUNDS = os.getenv("ALPHA_GEOCODE_BOUNDS") or "33.4,34.2;31.2,35.9"
# Nominatim's own confidence for a match; below this the answer is a guess and is not used.
GEOCODE_MIN_IMPORTANCE = float(os.getenv("ALPHA_GEOCODE_MIN_IMPORTANCE") or 0.25)
MAX_ATTACHMENT_MB = int(os.getenv("ALPHA_MAX_ATTACHMENT_MB") or 200)
