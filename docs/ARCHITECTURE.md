# Architecture Overview

This repository is organized as a lightweight monorepo with independently deployable services.

## Top-level layout
- services/
  - chat_api/ — Conversational AI FastAPI service (multi‑agent chat, conversations, summarization)
  - journal_api/ — Journaling and Mood Tracking FastAPI service
- frontend/ — Streamlit frontend (talks to services via HTTP)
- docs/ — Architecture and runbooks

Note: A legacy `backend/` directory exists; its contents have been duplicated into `services/chat_api` and will be retired.

## Services
### chat_api
- Purpose: chat endpoints, auth endpoints, conversation storage, summarization background task
- Tech: FastAPI, SQLAlchemy (async), Azure OpenAI, PostgreSQL (Cloud SQL), GCP Secret Manager
- Port: 8000
- Scaling: Cloud Run service `igethappy-chat-api`

### journal_api
- Purpose: user journaling and mood tracking
- Tech: FastAPI, SQLAlchemy (async), PostgreSQL (Cloud SQL), GCP Secret Manager, optional GCS for attachments
- Port: 8001
- Scaling: Cloud Run service `journal-api`

## Data
- Single PostgreSQL instance (Cloud SQL). Each service owns its tables:
  - chat_api: `users`, `chatbot_conversation_audit`, `chatbot_user_memory`
  - journal_api: `journal_entries`, `mood_logs`
- Indices for read paths:
  - `journal_entries(user_id, created_at desc)`
  - `mood_logs(user_id, logged_at desc)`

## Security & Secrets
- JWT bearer auth (tokens carry `sub` as user UUID)
- Secrets via GCP Secret Manager with env fallbacks (local dev)
- Principle of least privilege: per‑service service accounts with only needed roles

## Deployment
- Cloud Build config per service (`cloudbuild.yaml`)
- Cloud Run deploy scripts per service (`deploy.sh` and `deploy.bat`)
- Optionally front with API Gateway or HTTPS LB routing:
  - `/api/ai/*` → chat_api
  - `/api/journal/*`, `/api/mood/*` → journal_api

## Observability
- Structured logs via Cloud Run
- Health endpoints:
  - chat_api: `GET /health`
  - journal_api: `GET /health`

## Local development
- Run Postgres locally or via Cloud SQL Proxy
- Start services with `uvicorn` (ports 8000, 8001)
- Frontend points to services via `BASE_URL` env (or defaults to localhost)
