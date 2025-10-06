# chat_api (Conversational AI)

FastAPI service providing authentication, chat endpoints, and background summarization.

## Run locally
- Env: `DATABASE_URL`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT_NAME`
- Install: `pip install -r requirements.txt`
- Start: `uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- Docs: `http://localhost:8000/docs`

## Endpoints (selection)
- `GET /health`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `PUT /api/auth/profile`
- `POST /api/ai/start-conversation`
- `POST /api/ai/chat`

All protected routes use Bearer JWT (Authorization: `Bearer <token>`).

## Deploy (Cloud Run)
- Build & deploy via `deploy.sh` (Linux/macOS) or `deploy.bat` (Windows)
- Cloud Build config: `cloudbuild.yaml`
