# Verbatim App Backend

Backend-specific notes live here. The main project documentation is now in the repo-root `README.md`.

## Local Run

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```

Topic embeddings use hosted providers by default. Set `TOPIC_EMBEDDING_PROVIDER=gemini`
with `GEMINI_API_KEY`, or set `TOPIC_EMBEDDING_PROVIDER=openai` with `OPENAI_API_KEY`.
Embeddings are cached in memory per process, retried on transient provider errors, and can
fall back to OpenAI when `TOPIC_EMBEDDING_FALLBACK_PROVIDER=openai` and `OPENAI_API_KEY`
are set.

## Tests

```bash
cd backend
python -m unittest discover -s tests
```

## Render

```bash
build: cd backend && pip install -r requirements.txt
start: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
