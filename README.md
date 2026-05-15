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
|-- backend/     FastAPI app, analysis pipeline, auth, export logic
|-- frontend/    HTML, CSS, and browser-side JS
|-- scripts/     local repo maintenance and smoke-test helpers
`-- .python-version
```

## Requirements

- Python `3.12`
- Node.js for frontend lint/tests
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
TOPIC_EMBEDDING_FALLBACK_MODEL=text-embedding-3-small
TOPIC_EMBEDDING_FALLBACK_API_KEY=
OPENAI_API_KEY=...
NLTK_DATA=./nltk_data
TOPIC_INPUT_TRANSLATION_ENABLED=false
TOPIC_TRANSLATION_ENABLED=true
TOPIC_TRANSLATION_SOURCE_LANGUAGE=auto
TOPIC_TRANSLATION_TARGET_LANGUAGE=en
TOPIC_TRANSLATION_BATCH_SIZE=8
TOPIC_COMMUNITY_SIMILARITY_THRESHOLD=0.66
TOPIC_COMMUNITY_MAX_NEIGHBORS=16
TOPIC_COMMUNITY_RESOLUTION=0.9
TOPIC_COMMUNITY_MUTUAL_NEIGHBORS=false
TOPIC_AI_LABELING_ENABLED=true
TOPIC_AI_LABELING_MODEL=gemini-2.5-pro
TOPIC_AI_LABELING_TIMEOUT_SECONDS=30
TOPIC_AI_LABELING_MAX_GROUPS=30
TOPIC_AI_LABELING_BATCH_SIZE=5
TOPIC_AI_LABELING_MAX_EXAMPLES=15
TOPIC_AI_LABELING_MAX_TERMS=4
TOPIC_AI_LABELING_MAX_CHARS_PER_EXAMPLE=220
TOPIC_AI_LABELING_MAX_RETRIES=1
TOPIC_AI_LABELING_RETRY_BASE_SECONDS=0.75
TOPIC_AI_LABELING_CONSOLIDATE_SIMILAR_LABELS=false
RESULT_STORE_MAX_RESULTS=8
RESULT_STORE_TTL_SECONDS=10800
RESULT_STORE_CLEANUP_INTERVAL_SECONDS=60
```

To use OpenAI embeddings as the primary provider, set `TOPIC_EMBEDDING_PROVIDER=openai`, `OPENAI_API_KEY=...`, and optionally `TOPIC_EMBEDDING_MODEL=text-embedding-3-small`. If Gemini is primary and `OPENAI_API_KEY` is present, OpenAI can be used as the fallback when Gemini returns quota/rate errors.

AI topic labels use the tightest cluster responses plus capped term evidence. The default caps keep prompts focused: `TOPIC_AI_LABELING_MAX_EXAMPLES=15` and `TOPIC_AI_LABELING_MAX_TERMS=4`.

Deterministic backend consolidation merges matching labels, shared label bigrams/trigrams, and smaller groups that share the same two strongest top terms. Keep `TOPIC_AI_LABELING_CONSOLIDATE_SIMILAR_LABELS=false` unless you explicitly want an extra LLM call to consolidate generated labels.

Single-word verbatim responses are skipped before embeddings and clustering. This removes low-information rows such as `CVV`, `CCC`, or `hjhh`; it also removes valid one-word answers, so verbatim columns should contain sentence-style feedback for analysis.

For multilingual datasets, `TOPIC_INPUT_TRANSLATION_ENABLED=true` translates non-English responses before embeddings and clustering. Leave it `false` for faster analysis with original-language embeddings; the app still applies language-aware safeguards, but language-only clusters are more likely than with input translation enabled.

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
- result ids scoped to the signed browser session
- uploaded result ids cleared on logout

## Processing Model

The app is intentionally lightweight:

- uploaded results are held in memory during app runtime
- results are discarded on restart and logout
- users persist outputs by downloading reports
- no durable database is used for uploaded survey results
- old in-memory results expire by TTL and max-result limits

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

Configure Render from the service dashboard using the environment variables above.

Recommended Render build/start behavior:

```bash
build: cd backend && pip install -r requirements.txt
start: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Important:

- Python is pinned via `.python-version`
- Render should include the result-store, embedding, community, and AI-labeling env vars listed above when testing memory and label quality
- topic embeddings use Gemini/OpenAI API providers by default, avoiding large model downloads during build
- frontend assets are served by FastAPI from the top-level `frontend/` directory

After deploying config changes that affect labels or clustering, rerun the analysis in the app. Existing in-memory analysis results are not rewritten automatically.

## Testing

Backend checks from the repo root:

```bash
python scripts/check_architecture.py
python -m ruff check backend/app backend/tests
python -m mypy
python -m unittest discover -s backend/tests -t backend
```

Frontend syntax checks:

```bash
node --check ../frontend/results.js
node --check ../frontend/results/analysis.js
node --check ../frontend/results/charts.js
node --check ../frontend/results/modals.js
node --check ../frontend/upload.js
```

Frontend lint and unit tests:

```bash
cd frontend
npm install
npm run lint -- --max-warnings=0
npm test
```

Static frontend smoke test from the repo root:

```bash
python scripts/smoke_frontend_static.py
```

The smoke test starts the FastAPI app locally, verifies anonymous users land on `/login`, then recursively checks the CSS import graph and browser ES module graph.

## Local Artifacts

The repo ignores local caches, generated reports, temporary review folders, logs, and large ad hoc exports. Keep throwaway work in ignored locations such as `junk/`, `.qodo/`, `.review-friday/`, or local `*.zip`/`*.log` files so the tracked tree stays focused on source, tests, docs, and deployment config.

## Known Constraints

- very large files can still take time because embeddings are generated through hosted APIs before community detection runs
- uploaded results are not durable across app restarts
- only the active session result is retained for the signed browser session; replacing an upload purges previous session result ids
- the app is intended for a small internal user group, not large-scale concurrent analysis

## Current User Flow

1. Upload CSV
2. Review detected columns
3. Reassign columns if needed
4. Run analysis
5. Filter/explore results
6. Inspect representative responses
7. Export report
