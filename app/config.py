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
DB_PATH = os.getenv("ALPHA_DB_PATH") or _default_db_path()
REQUEST_TIMEOUT = int(os.getenv("ALPHA_REQUEST_TIMEOUT") or 120)

# ── Model providers ───────────────────────────────────────────────────────────
# Any number of OpenAI-compatible providers can be configured, tried in order. When one
# reports a spent quota it is set aside and the next is used, so a free daily limit on any
# single provider does not stop work. Two ways to declare them:
#
#   LLM_PROVIDERS=1,2,3          which numbers exist, in the order to try them
#   LLM_1_URL / LLM_1_KEY / LLM_1_MODEL / LLM_1_VISION_MODEL
#   LLM_2_URL / ...              the next provider, and so on
#
# The older LLM_* / BACKUP_LLM_* names still work: they become providers 1 and 2 when
# LLM_PROVIDERS is not set, so an existing .env keeps working unchanged.
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


def _declared_providers():
    """Providers in the order they should be tried."""
    listed = (os.getenv("LLM_PROVIDERS") or "").strip()
    if listed:
        indexes = [part.strip() for part in listed.split(",") if part.strip()]
        return [_provider(i, os.getenv(f"LLM_{i}_URL"), os.getenv(f"LLM_{i}_KEY"),
                          os.getenv(f"LLM_{i}_MODEL"), os.getenv(f"LLM_{i}_VISION_MODEL") or "",
                          label=os.getenv(f"LLM_{i}_LABEL") or "")
                for i in indexes]
    # Legacy two-provider layout.
    return [
        _provider("1", os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
                  os.getenv("LLM_API_KEY"), os.getenv("LLM_MODEL") or "gpt-4.1-mini",
                  os.getenv("VISION_MODEL") or ""),
        _provider("2", os.getenv("BACKUP_LLM_BASE_URL"), os.getenv("BACKUP_LLM_API_KEY"),
                  os.getenv("BACKUP_LLM_MODEL"), os.getenv("BACKUP_VISION_MODEL") or ""),
    ]


PROVIDERS = [p for p in _declared_providers() if p]

# Kept for the health check and messages: the first provider is the main one.
LLM_BASE_URL = PROVIDERS[0]["url"] if PROVIDERS else "https://api.openai.com/v1"
LLM_MODEL = PROVIDERS[0]["model"] if PROVIDERS else "gpt-4.1-mini"
LLM_API_KEY = PROVIDERS[0]["key"] if PROVIDERS else ""
VISION_MODEL = PROVIDERS[0]["vision_model"] if PROVIDERS else ""
VISION_BASE_URL = LLM_BASE_URL
VISION_API_KEY = LLM_API_KEY
BACKUP_BASE_URL = PROVIDERS[1]["url"] if len(PROVIDERS) > 1 else ""
BACKUP_API_KEY = PROVIDERS[1]["key"] if len(PROVIDERS) > 1 else ""
BACKUP_MODEL = PROVIDERS[1]["model"] if len(PROVIDERS) > 1 else ""


def backup_ready():
    return len(PROVIDERS) > 1

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
