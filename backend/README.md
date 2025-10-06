# Conversational AI Backend

A FastAPI-based backend for a conversational AI application that integrates with Azure OpenAI and Google Cloud SQL (PostgreSQL).

## Features

- **FastAPI Framework**: Modern, fast web framework for building APIs
- **Azure OpenAI Integration**: Uses Azure OpenAI API for generating AI responses
- **Google Cloud SQL**: PostgreSQL database hosted on Google Cloud
- **Google Cloud Secret Manager**: Secure secret management
- **Async/Await Support**: Fully asynchronous database operations
- **Authentication**: Bearer token authentication (configurable)
- **Conversation Management**: Track and manage chat conversations
- **Message History**: Store and retrieve conversation history

## Project Structure

```
backend/
├── main.py             # FastAPI application and core chat endpoint
├── database.py         # SQLAlchemy models and async database session setup
├── schemas.py          # Pydantic models for API request/response validation
├── config.py           # Configuration and loading secrets from GCP Secret Manager
├── crud.py             # Functions for all database operations (CRUD)
├── requirements.txt    # Python package dependencies
└── README.md          # This file
```

## Database Schema

### chatbot_conversation_audit
- `conversation_id` (UUID, Primary Key)
- `user_id` (UUID, Not Null)
- `title` (Text)
- `conversation_summary` (Text)
- `model` (Text)
- `token_usage` (JSONB)
- `status` (Text, Default: 'in-progress')
- `last_message_at` (TIMESTAMPTZ)
- `created_at` (TIMESTAMPTZ, Default: NOW())
- `archived` (Boolean, Default: FALSE)

### chatbot_user_memory
- `id` (UUID, Primary Key, Default: gen_random_uuid())
- `conversation_id` (UUID, Foreign Key)
- `user_id` (UUID, Not Null)
- `role` (Text, Check: 'user' or 'assistant')
- `content` (JSONB, Not Null)
- `created_at` (TIMESTAMPTZ, Default: NOW())

## Setup Instructions

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Google Cloud

1. Set up a Google Cloud project
2. Enable the Secret Manager API
3. Create secrets in Secret Manager for:
   - `database-url`: Your PostgreSQL connection string
   - `azure-openai-api-key`: Your Azure OpenAI API key
   - `azure-openai-endpoint`: Your Azure OpenAI endpoint URL
   - `azure-openai-deployment-name`: Your Azure OpenAI deployment name

### 3. Environment Variables

Set the following environment variables:

```bash
export GCP_PROJECT_ID="your-gcp-project-id"
export DATABASE_URL_SECRET_NAME="database-url"
export AZURE_OPENAI_API_KEY_SECRET_NAME="azure-openai-api-key"
export AZURE_OPENAI_ENDPOINT_SECRET_NAME="azure-openai-endpoint"
export AZURE_OPENAI_DEPLOYMENT_NAME_SECRET_NAME="azure-openai-deployment-name"
```

### 4. Database Setup

Create the required tables in your PostgreSQL database:

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create conversation audit table
CREATE TABLE chatbot_conversation_audit (
    conversation_id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    title TEXT,
    conversation_summary TEXT,
    model TEXT,
    token_usage JSONB,
    status TEXT DEFAULT 'in-progress' NOT NULL,
    last_message_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    archived BOOLEAN DEFAULT FALSE NOT NULL
);

-- Create user memory table
CREATE TABLE chatbot_user_memory (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES chatbot_conversation_audit(conversation_id),
    user_id UUID NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 5. Run the Application

```bash
python main.py
```

Or with uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## API Endpoints

### POST /api/ai/chat

Main chat endpoint for interacting with the AI.

**Request:**
```json
{
    "conversation_id": "optional-uuid",
    "message": "Hello, how are you?"
}
```

**Response:**
```json
{
    "conversation_id": "uuid",
    "response": "I'm doing well, thank you for asking!"
}
```

### GET /api/conversations/{conversation_id}

Get conversation details and message history.

**Response:**
```json
{
    "conversation": {
        "conversation_id": "uuid",
        "user_id": "uuid",
        "title": "Hello, how are you?",
        "status": "in-progress",
        "created_at": "2024-01-01T00:00:00Z",
        "archived": false
    },
    "messages": [
        {
            "id": "uuid",
            "role": "user",
            "content": {"text": "Hello, how are you?"},
            "created_at": "2024-01-01T00:00:00Z"
        }
    ]
}
```

### GET /health

Health check endpoint.

**Response:**
```json
{
    "status": "healthy",
    "timestamp": "2024-01-01T00:00:00Z"
}
```

## Authentication

The API uses Bearer token authentication. Include the token in the Authorization header:

```
Authorization: Bearer your-token-here
```

**Note:** The current implementation uses a hardcoded user ID for demonstration purposes. In production, you should implement proper token validation and user extraction.

## Error Handling

The API returns appropriate HTTP status codes and error messages:

- `400 Bad Request`: Invalid request data
- `401 Unauthorized`: Missing or invalid authentication
- `404 Not Found`: Conversation not found
- `500 Internal Server Error`: Server or external service errors

## Development

### Running in Development Mode

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### API Documentation

Once the server is running, visit:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Production Considerations

1. **Security**: Implement proper authentication and authorization
2. **Rate Limiting**: Add rate limiting to prevent abuse
3. **Monitoring**: Add logging and monitoring
4. **CORS**: Configure CORS appropriately for your frontend
5. **Database Connection Pooling**: Tune connection pool settings
6. **Error Handling**: Implement comprehensive error handling
7. **Secrets Management**: Use proper secret rotation policies

## Proxy Pattern (Server-to-Server)

FastAPI endpoints for chat are protected by an internal API key passed via `X-API-Key`. Your server (Node/Edge) authenticates the user with Flutter, then forwards requests to FastAPI.

- Header: `X-API-Key: <INTERNAL_API_KEY>`
- Requests:
  - Start conversation:
    ```
    { "client_user_id": "<uuid>", "history": ["hi", "hello"] }
    ```
  - Chat message:
    ```
    { "conversation_id": "<uuid>", "user_message": "hi", "client_user_id": "<uuid>", "history": ["..."] }
    ```
- Response:
  ```
  { "conversation_id": "<uuid>", "ai_response": "...", "usage": { }, "meta": { "model": "..." } }
  ```

### Environment

- `INTERNAL_API_KEY`: required; set via Secret Manager or env
- `DATABASE_URL`: Postgres URL (Cloud SQL or local)
- `VERTEX_PROJECT_ID`, `VERTEX_LOCATION`, `VERTEX_MODEL`: Vertex AI settings
- `ALLOWED_ORIGINS`: comma-separated CORS origins (e.g., `https://your-frontend.example.com`)

### CORS

CORS origins are configurable via `ALLOWED_ORIGINS`. Defaults to `*` if unset. Set this to your server/frontend domains in production.

### Smoke Tests

Start a conversation:
```
curl -X POST http://localhost:8000/api/ai/start-conversation \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -d '{"client_user_id":"2f1a4d4e-8c36-4c5c-9b1b-6a3b6a4a1b2c"}'
```

Send a chat message:
```
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $INTERNAL_API_KEY" \
  -d '{"conversation_id":"<conv-uuid>","user_message":"Hello","client_user_id":"2f1a4d4e-8c36-4c5c-9b1b-6a3b6a4a1b2c"}'
```