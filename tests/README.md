# Alpha — how to run the tests

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt pytest httpx2   # Windows
# python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest httpx2   # macOS/Linux
```

```bash
.venv/Scripts/python.exe -m pytest tests -q
```

On a Windows terminal that shows Arabic as `????`, add `PYTHONIOENCODING=utf-8` in front.

The suite takes about 35 seconds and needs no Docker, no n8n and no API key: every network
call is either stubbed or answered by a local HTTP server that mimics the workflow's contract.

| File | What it covers |
| --- | --- |
| `test_db.py` | Schema, case/message/attachment CRUD, case numbering, search, filters, CSV export |
| `test_attachments.py` | Safe file names (no path traversal), size limits, kinds, save/read/remove |
| `test_extract.py` | Text/PDF/DOCX reading, image shrinking, vision descriptions and their cache |
| `test_vision` (in `test_extract.py`) | Missing provider, HTTP errors, empty answers, a crashing worker |
| `test_llm.py` | Quota detection, provider ordering, cooldowns, `chat_completions` rotation |
| `test_analysis.py` | Report parsing, severity, n8n errors, quota fallback, suggestions |
| `test_chat.py` | Conversation history, payload building, background replies, retry, clear |
| `test_i18n.py` | Every translation string in both languages, placeholder parity, and label helpers |
| `test_n8n_contract.py` | The app against a local server that mimics the workflow end to end |
| `test_workflow_expressions.py` | The n8n workflow's own expressions: URL suffix, non-nested model expression, per-provider routing |
| `test_live_vision.py` | **Skipped unless asked for.** Real providers, real workflow: one image, one video, one full analysis |

`test_workflow_expressions.py` is the guard for the provider bug: n8n rejects a `{{ }}` nested
inside another expression, and the URL expression must append `/chat/completions`.

## Live run (spends real quota)

```bash
ALPHA_LIVE=1 ALPHA_LIVE_PROVIDER=3 python -m pytest tests/test_live_vision.py -q
```

`ALPHA_LIVE_PROVIDER` pins one provider by its index in `LLM_PROVIDERS` and sets the others
aside for the run; leave it out to let the normal rotation decide. The live run needs `.env`
credentials and n8n up at `ALPHA_WEBHOOK_URL` (default `http://localhost:5678/webhook/alpha-analyze`).
