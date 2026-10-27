# Alpha Investigation System

Alpha is a bilingual (Arabic and English) application for managing investigation cases and reviewing AI-assisted analysis. Users can organize case details, work with supporting files, chat about case information, and view incident locations on a map.

The React interface runs on port `8601` and communicates with a FastAPI backend. The backend stores case data and attachments in SQLite and sends analysis requests to an n8n workflow. n8n uses PostgreSQL for its workflows and execution data. The former Streamlit interface has been removed.

The interface and generated analysis are available in Arabic and English. The About page includes developer information and contact links.

## Architecture

```text
Browser :8601 -> React + nginx -> FastAPI :8000 -> n8n :5678 -> language / vision model
                                     |
                                SQLite + attachments

n8n -> PostgreSQL
```

- **Web:** React application served by nginx on port `8601`; nginx forwards `/api` requests to FastAPI.
- **API:** FastAPI service that uses the shared analysis, chat, and attachment modules in `app/`.
- **n8n:** Runs the workflow in `n8n/workflows/alpha-analysis.json`. The workflow is imported and published automatically at startup.
- **PostgreSQL:** Stores n8n workflows and execution data.
- **SQLite:** Stores investigation cases, messages, reports, and attachment metadata.

## Requirements

- Docker Desktop, or Docker Engine with Docker Compose v2.20 or later.
- An API key for an OpenAI-compatible provider (such as OpenAI, Gemini, Anthropic, Groq, or OpenRouter), or a locally running Ollama instance.

## Quick start

### 1. Clone the repository

```bash
git clone https://github.com/3bdallah2004/AlphaSystem.git
cd AlphaSystem
```

### 2. Configure the environment

```bash
cp .env.example .env
```

On Windows, use `copy .env.example .env`. Set `LLM_API_KEY` and choose a private value for `POSTGRES_PASSWORD` in `.env`.

### 3. Start the application

| Platform | Command |
|---|---|
| Windows | Run `run_alpha.bat` |
| macOS / Linux | `bash run_alpha.sh` |
| Any platform | `docker compose up -d --build --wait --remove-orphans` |

The startup scripts check Docker, create `.env` from `.env.example` if needed, wait for the services to become healthy, and open the website.

Open **http://localhost:8601**.

### Stop the application

```bash
docker compose down       # Stop containers and preserve data
docker compose down -v    # WARNING: also delete case and n8n data volumes
```

## AI provider configuration

The workflow supports any OpenAI-compatible Chat Completions API. Configure providers in `.env`, then restart the services with `docker compose up -d`.

| Provider | `LLM_BASE_URL` | Example `LLM_MODEL` |
|---|---|---|
| OpenAI | `https://api.openai.com/v1` | `gpt-4.1-mini` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-2.5-flash` |
| Anthropic | `https://api.anthropic.com/v1` | `claude-sonnet-5-5` |
| Groq | `https://api.groq.com/openai/v1` | `llama-3.3-70b-versatile` |
| OpenRouter | `https://openrouter.ai/api/v1` | `openai/gpt-4.1-mini` |
| Ollama | `http://host.docker.internal:11434/v1` | `llama3.1` |

For Ollama, `LLM_API_KEY` can contain any value; Ollama does not use it.

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `LLM_API_KEY` | Provider API key; required for AI analysis | — |
| `LLM_BASE_URL` | Provider API base URL | `https://api.openai.com/v1` |
| `LLM_MODEL` | Text analysis model | `gpt-4.1-mini` |
| `LLM_PROVIDERS` and `LLM_<n>_URL` / `_KEY` / `_MODEL` / `_VISION_MODEL` | Configure multiple providers in priority order | — |
| `BACKUP_LLM_BASE_URL` / `BACKUP_LLM_API_KEY` / `BACKUP_LLM_MODEL` | Configure a second provider using the legacy variable names | — |
| `ALPHA_WEBHOOK_TOKEN` | Shared secret required by the app and n8n; startup scripts generate one if missing | Empty means no webhook authentication |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | n8n database credentials | `n8n` / required / `n8n` |
| `TIMEZONE` | Time zone used by n8n | `UTC` |
| `WEB_PORT` / `N8N_PORT` | Host ports for the website and n8n | `8601` / `5678` |
| `ALPHA_REQUEST_TIMEOUT` | Analysis request timeout in seconds | `120` |
| `VISION_MODEL` | Model used to inspect image and video attachments | `nvidia/nemotron-3.5-super-vl:free` |
| `VISION_BASE_URL` / `VISION_API_KEY` | Vision provider; defaults to the text provider | — |
| `ALPHA_VISION_ENABLED` | Set to `0` to disable attachment vision analysis | `1` |
| `ALPHA_VISION_MAX_TOKENS` | Initial vision response token budget | `1200` |
| `ALPHA_VISION_RETRY_MAX_TOKENS` | Token budget for a vision retry | `3000` |
| `ALPHA_GEOCODE_ENABLED` | Set to `0` to disable automatic location lookup | `1` |
| `ALPHA_GEOCODE_URL` | Place-name geocoding service | OpenStreetMap Nominatim |
| `ALPHA_GEOCODE_BOUNDS` | Preferred bounds in `north,west;south,east` format | `33.4,34.2;31.2,35.9` |
| `ALPHA_MAX_ATTACHMENT_MB` | Maximum size of each attachment | `200` |
| `ALPHA_ATTACHMENTS_DIR` | Attachment storage directory (without Docker) | Next to the database |
| `ALPHA_WEBHOOK_URL` | n8n workflow URL (without Docker) | `http://localhost:5678/webhook/alpha-analyze` |
| `ALPHA_DB_PATH` | SQLite database path (without Docker) | `data/alpha_database.db` |

By default, the website and n8n ports are bound to `127.0.0.1` and are not exposed to the local network.

## Local development

For live-reload development, start n8n first:

```powershell
docker compose up -d --wait n8n
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
$env:ALPHA_WORKER = "api"
uvicorn api.main:app --reload --port 8000
```

In a second terminal:

```bash
cd web
npm ci
npm run dev
```

The Vite development server runs at `http://localhost:5173` and proxies `/api` requests to FastAPI on port `8000`.

## Case conversations

After analysis, each case has a report and a conversation. Users can ask questions about the case, add information, and attach files to messages. Responses use the original report, the latest analysis, and up to the last 20 conversation messages.

- Replies are generated in the background so users can continue working.
- Failed replies can be retried without losing the original question.
- A reply can be added to the case report while preserving previous report versions.
- Clearing a conversation removes its messages and message attachments without deleting case attachments.
- Pending replies are marked as failed after a service restart and can be retried.

## Attachments and multimodal analysis

Cases support images, video, audio, PDF, Word documents, and text files, subject to `ALPHA_MAX_ATTACHMENT_MB` (200 MB by default per file). Attachments are stored under `data/attachments/<case-id>/` in the same Docker volume as the case database and are removed when the case is deleted.

| File type | Processing |
|---|---|
| Text, CSV, JSON, HTML, SVG | Read as text |
| PDF | Text extracted with `pypdf` |
| Word (`.docx`) | Text extracted with `python-docx` |
| Images | Described by the configured vision model |
| Video | Up to four frames are extracted with `ffmpeg` and analyzed by the vision model |
| Audio | Transcribed through a provider that supports `/audio/transcriptions` |

Vision descriptions and audio transcriptions are cached to avoid repeating work during re-analysis. Unreadable or unsupported attachments are reported rather than silently ignored. Set `ALPHA_VISION_ENABLED=0` to exclude attachments from vision analysis.

## Maps and locations

- Case locations can be geocoded automatically from a place name using OpenStreetMap Nominatim, or selected manually on the map.
- The map displays case locations in case details and in the filtered case register.
- A click on the map replaces the automatically selected pin; users can also remove the pin.
- By default, geocoding prefers the West Bank region using `ALPHA_GEOCODE_BOUNDS`.
- Only the place name is sent to Nominatim; case report text and other case details are not sent.
- Map tiles are loaded from public OpenStreetMap servers. For sensitive deployments, consider hosting your own tile server.

## Editing the n8n workflow

1. Open **http://localhost:5678** and create the owner account on first launch.
2. Edit the **Alpha - Case Analysis** workflow and publish your changes.
3. Download the updated workflow and replace `n8n/workflows/alpha-analysis.json` in the repository.

The repository workflow is imported at startup, so save workflow changes in the repository to keep them across restarts.

## Project structure

```text
AlphaSystem/
├── app/                       # Shared analysis, database, chat, and attachment modules
├── api/                       # FastAPI backend used by React
├── web/                       # React website
├── n8n/workflows/             # Analysis and conversation workflow
├── Dockerfile.api             # FastAPI container image
├── docker-compose.yml         # PostgreSQL, n8n, API, and website services
├── requirements.txt           # Python dependencies
├── .env.example               # Environment template
├── run_alpha.bat              # Windows startup script
└── run_alpha.sh               # macOS / Linux startup script
```

## Troubleshooting

| Problem | Suggested action |
|---|---|
| Workflow is missing or inactive | Run `docker compose up -d` and check `docker compose logs n8n-import`. |
| No AI provider is configured | Set `LLM_API_KEY` or `LLM_1_KEY` in `.env`, then restart the services. |
| Invalid provider credentials (`401`) | Check that the API key matches the configured `LLM_BASE_URL`. |
| Model not found (`404`) | Check that `LLM_MODEL` is available from the selected provider. |
| Webhook token is rejected | Ensure `ALPHA_WEBHOOK_TOKEN` matches for the API and n8n, then run `docker compose up -d`. |
| PostgreSQL password is missing | Create `.env` from `.env.example` and set `POSTGRES_PASSWORD`. |
| Port `8601` or `5678` is in use | Change `WEB_PORT` or `N8N_PORT` in `.env`. |
| Environment changes are not applied | Recreate services with `docker compose up -d`. |

View service logs with `docker compose logs -f web api n8n`.

## Developer

Abdullah Haj Ali — [@3bdallah2004](https://github.com/3bdallah2004)
