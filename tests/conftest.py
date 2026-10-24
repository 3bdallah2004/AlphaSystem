"""Shared fixtures: every test runs against a throwaway database and attachments folder.

Environment is set before `config` is imported anywhere, because config reads it once at
import time and db.py binds DB_PATH at import as well.
"""
import os
import sys
import tempfile
from pathlib import Path

import pytest

APP_DIR = Path(__file__).resolve().parent.parent / "app"
sys.path.insert(0, str(APP_DIR))

LIVE = os.getenv("ALPHA_LIVE") == "1"

_TMP = tempfile.mkdtemp(prefix="alpha-tests-")
# Data always goes to a throwaway folder, live run or not.
os.environ["ALPHA_DB_PATH"] = str(Path(_TMP) / "test.db")
os.environ["ALPHA_ATTACHMENTS_DIR"] = str(Path(_TMP) / "attachments")
os.environ["ALPHA_VISION_ENABLED"] = "1"

if LIVE:
    # A live run uses the real providers from .env and the real workflow.
    os.environ.setdefault("ALPHA_WEBHOOK_URL", "http://localhost:5678/webhook/alpha-analyze")
    os.environ["ALPHA_REQUEST_TIMEOUT"] = "180"
else:
    # Default run: no network at all. A provider has to exist for llm/vision to offer
    # anything, and nothing ever calls it.
    os.environ["ALPHA_WEBHOOK_URL"] = "http://127.0.0.1:9/webhook/alpha-analyze"
    os.environ["ALPHA_REQUEST_TIMEOUT"] = "5"
    # No place lookups either; the tests that exercise geocoding patch the module directly.
    os.environ["ALPHA_GEOCODE_ENABLED"] = "0"
    os.environ["LLM_PROVIDERS"] = "1"
    os.environ["LLM_1_URL"] = "http://127.0.0.1:9/v1"
    os.environ["LLM_1_KEY"] = "test-key"
    os.environ["LLM_1_MODEL"] = "test-model"
    os.environ["LLM_1_VISION_MODEL"] = "test-vision"


@pytest.fixture()
def database():
    """A freshly created database for one test."""
    import db as db_module

    path = Path(os.environ["ALPHA_DB_PATH"])
    path.unlink(missing_ok=True)
    db_module.init_db()
    yield db_module
    if path.exists():
        path.unlink(missing_ok=True)


@pytest.fixture()
def case(database):
    """One draft case."""
    case_id = database.create_draft("بلاغ تجريبي عن حادثة سرقة في المستودع المركزي ليلاً.")
    database.update_case(case_id, case_name="قضية تجريبية", case_number="ALP-2026-001")
    return case_id
