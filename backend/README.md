# Verbatim App Backend

Backend-specific notes live here. The main project documentation is in the repo-root `README.md`.

## Local Run

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Topic embeddings use hosted providers by default. Set `TOPIC_EMBEDDING_PROVIDER=gemini`
with `GEMINI_API_KEY`, or set `TOPIC_EMBEDDING_PROVIDER=openai` with `OPENAI_API_KEY`.
Embeddings are cached in memory per process, retried on transient provider errors, and can
fall back to OpenAI when `TOPIC_EMBEDDING_FALLBACK_PROVIDER=openai` and `OPENAI_API_KEY`
or `TOPIC_EMBEDDING_FALLBACK_API_KEY` are set.

AI labels can be consolidated during label creation with:

```bash
TOPIC_AI_LABELING_CONSOLIDATE_SIMILAR_LABELS=true
```

That call sends generated labels and counts, not raw responses, and returns group ids that should share a canonical label. The normal backend merge step then aggregates counts, examples, documents, and chart group ids.

## In-Memory Results

Uploaded datasets and analysis outputs are kept in process memory. The store is bounded by:

```bash
RESULT_STORE_MAX_RESULTS=8
RESULT_STORE_TTL_SECONDS=900
RESULT_STORE_CLEANUP_INTERVAL_SECONDS=60
```

Session auth tracks the active result ids for the signed browser session. Uploading a replacement result clears older ids for that session, and logout purges the session's active ids.

## Tests

From the repo root:

```bash
python scripts/check_architecture.py
python -m ruff check backend/app backend/tests
python -m mypy
python -m unittest discover -s backend/tests -t backend
```

## Render

```bash
build: cd backend && pip install -r requirements.txt
start: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

The repo-level `render.yaml` also downloads NLTK stopwords during build and configures the default embedding, community, AI-labeling, and result-store settings used in production.
