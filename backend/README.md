# Verbatim App Backend

Backend-specific notes live here. The main project documentation is now in the repo-root `README.md`.

## Local Run

```bash
cd backend
pip install -r requirements.txt
python download_topic_model.py
python -m uvicorn app.main:app --reload
```

## Tests

```bash
cd backend
python -m unittest discover -s tests
```

## Render

```bash
build: cd backend && pip install -r requirements.txt && python download_topic_model.py
start: cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT
```
