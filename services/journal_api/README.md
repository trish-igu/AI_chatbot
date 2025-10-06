# journal_api (Journaling & Mood Tracking)

FastAPI service for journal entries and mood logs.

## Run locally
- Env: `DATABASE_URL`, `JWT_SECRET_KEY`, optional `GCS_BUCKET_NAME`
- Install: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port 8001 --reload`
- Docs: `http://localhost:8001/docs`

## Endpoints
- `POST /api/journal/entries` — create journal entry
- `GET /api/journal/entries` — list entries (by authenticated user)
- `POST /api/mood/logs` — create mood log

JWT bearer required (Authorization: `Bearer <token>`; token `sub` is user UUID).

## Deploy (Cloud Run)
- Build & deploy via `deploy.sh` (Linux/macOS) or `deploy.bat` (Windows)
- Cloud Build config: `cloudbuild.yaml`
