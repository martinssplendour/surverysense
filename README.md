# Verbatim App

Internal verbatim-analysis app for uploading CSV survey data, selecting freeform text columns, running topic modelling, and exporting stakeholder-ready reports.

The app is designed for small-team internal use. It runs on a single Render web service and does not use durable server-side storage for uploaded results.

## What It Does

- uploads and ingests messy CSV survey exports
- detects likely metadata and verbatim columns
- lets users reassign columns when detection is wrong
- runs analysis with:
  - `Community Detection`
  - `N-grams`
- supports metadata filtering
- shows interactive charts
- lets users inspect representative responses and matching documents
- exports reports as:
  - `PDF`
  - `DOCX`
  - `PPTX`

## Repo Structure

```text
.
├── backend/     FastAPI app, analysis pipeline, auth, export logic
├── frontend/    HTML, CSS, and browser-side JS
├── render.yaml  Render deployment config
└── .python-version
```

## Requirements

- Python `3.12`
- Bash-compatible shell for the commands below

## Local Setup

From the repo root:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Open:

```text
http://127.0.0.1:8000
```

## Environment Variables

Copy `backend/.env.example` to `backend/.env`.

Minimum useful setup:

```bash
SESSION_SECRET=change-me-to-a-random-secret
SESSION_HTTPS_ONLY=false
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_ALLOWED_DOMAINS=twinkl.co.uk,twinkl.com
```

`SESSION_SECRET` is required in every environment; the app no longer falls back to an in-code default.

Optional but recommended:

```bash
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TEMPERATURE=0.1
GEMINI_TIMEOUT_SECONDS=60
TOPIC_EMBEDDING_PROVIDER=gemini
TOPIC_EMBEDDING_MODEL=gemini-embedding-001
TOPIC_EMBEDDING_DIMENSIONS=768
TOPIC_EMBEDDING_BATCH_SIZE=128
TOPIC_EMBEDDING_TIMEOUT_SECONDS=60
TOPIC_EMBEDDING_MAX_RETRIES=1
TOPIC_EMBEDDING_CACHE_SIZE=4096
TOPIC_EMBEDDING_FALLBACK_PROVIDER=openai
OPENAI_API_KEY=...
TOPIC_TRANSLATION_ENABLED=true
TOPIC_TRANSLATION_SOURCE_LANGUAGE=auto
TOPIC_TRANSLATION_TARGET_LANGUAGE=en
TOPIC_TRANSLATION_BATCH_SIZE=8
TOPIC_COMMUNITY_SIMILARITY_THRESHOLD=0.62
TOPIC_COMMUNITY_MAX_NEIGHBORS=12
TOPIC_AI_LABELING_ENABLED=true
TOPIC_AI_LABELING_TIMEOUT_SECONDS=30
TOPIC_AI_LABELING_MAX_GROUPS=15
TOPIC_AI_LABELING_BATCH_SIZE=5
TOPIC_AI_LABELING_MAX_EXAMPLES=6
TOPIC_AI_LABELING_MAX_CHARS_PER_EXAMPLE=220
TOPIC_AI_LABELING_MAX_RETRIES=1
TOPIC_AI_LABELING_RETRY_BASE_SECONDS=0.75
```

To use OpenAI embeddings as the primary provider, set `TOPIC_EMBEDDING_PROVIDER=openai`, `OPENAI_API_KEY=...`, and optionally `TOPIC_EMBEDDING_MODEL=text-embedding-3-small`. If Gemini is primary and `OPENAI_API_KEY` is present, OpenAI can be used as the fallback when Gemini returns quota/rate errors.

Useful session settings:

```bash
SESSION_IDLE_TIMEOUT_SECONDS=1800
```

## Auth

The app uses Google OAuth and only allows users from configured Twinkl domains.

Current auth model:

- cookie-based session auth
- secure-cookie support via `SESSION_HTTPS_ONLY`
- session rotation on login
- idle session expiry
- uploaded result ids cleared on logout

## Processing Model

The app is intentionally lightweight:

- uploaded results are held in memory during app runtime
- results are discarded on restart and logout
- users persist outputs by downloading reports
- no durable database is used for uploaded survey results

This means the app is close to stateless in product behavior, but it is not strictly stateless at the server-process level.

## Analysis Modes

### Community Detection

Builds a similarity network from response embeddings, detects natural communities, and adds a `community_group` column to the clean data after analysis.

### N-grams

Best when you want a quick view of repeated words and phrases rather than clustered topics.

## Report Export

Exports are available after a successful analysis run.

Supported formats:

```text
PDF
DOCX
PPTX
```

Reports include:

- chart images
- grouped topic summaries
- representative documents

## Render Deployment

The repo includes `render.yaml`.

Render build/start behavior:

```bash
build: cd backend && pip install -r requirements.txt && python -m nltk.downloader -d ./nltk_data stopwords
start: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Important:

- Python is pinned via `.python-version`
- NLTK stopwords are downloaded during the Render build and exposed with `NLTK_DATA=./nltk_data`
- topic embeddings use Gemini/OpenAI API providers by default, avoiding large model downloads during build
- frontend assets are served by FastAPI from the top-level `frontend/` directory

## Testing

Backend:

```bash
cd backend
python -m unittest discover -s tests
```

Frontend syntax checks:

```bash
node --check ../frontend/results.js
node --check ../frontend/results/analysis.js
node --check ../frontend/results/charts.js
node --check ../frontend/results/modals.js
node --check ../frontend/upload.js
```

## Known Constraints

- very large files can still take time because embeddings are generated through hosted APIs before community detection runs
- uploaded results are not durable across app restarts
- the app is intended for a small internal user group, not large-scale concurrent analysis

## Current User Flow

1. Upload CSV
2. Review detected columns
3. Reassign columns if needed
4. Run analysis
5. Filter/explore results
6. Inspect representative responses
7. Export report
