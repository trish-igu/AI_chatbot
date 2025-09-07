"""
FastAPI application and the core chat endpoint, corrected for the final schema.
"""
import uuid
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from openai import AsyncAzureOpenAI, APIError
from contextlib import asynccontextmanager
import logging

from database import get_db, init_database, close_database
from schemas import ChatRequest, ChatResponse, HealthResponse
from crud import (
    get_or_create_user,
    get_conversation, 
    create_conversation, 
    update_conversation_timestamp,
    get_message_history,
    save_message
)
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app_state = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("Application startup...")
    await init_database(settings.database_url)
    
    app_state["azure_openai_client"] = AsyncAzureOpenAI(
        api_key=settings.azure_openai_api_key,
        api_version="2024-02-15-preview",
        azure_endpoint=settings.azure_openai_endpoint
    )
    logger.info("Azure OpenAI client initialized successfully")
    
    yield
    
    logger.info("Application shutdown...")
    await close_database()
    logger.info("Application shutdown complete")

app = FastAPI(
    title="Conversational AI Backend",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

async def get_azure_openai_client() -> AsyncAzureOpenAI:
    return app_state["azure_openai_client"]

DEV_USER_ID = str(uuid.uuid4())
logger.info(f"Using fixed development user ID: {DEV_USER_ID}")

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    if not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authentication credentials")
    return DEV_USER_ID

@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="healthy")

@app.post("/api/ai/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    client: AsyncAzureOpenAI = Depends(get_azure_openai_client)
):
    try:
        user_id = uuid.UUID(current_user)
        conversation_id = request.conversation_id
        user_message = request.message
        
        await get_or_create_user(db, user_id)
        
        if conversation_id:
            conversation = await get_conversation(db, conversation_id, user_id)
            if not conversation:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
            message_history = await get_message_history(db, conversation_id)
        else:
            title = user_message[:60]
            conversation = await create_conversation(db, user_id, title)
            conversation_id = conversation.conversation_id
            message_history = []
        
        messages = [{"role": "system", "content": "You are a helpful AI assistant."}]
        for msg in message_history:
            messages.append({"role": msg.role, "content": msg.content.get("text", "")})
        messages.append({"role": "user", "content": user_message})

        try:
            response = await client.chat.completions.create(model=settings.azure_openai_deployment_name, messages=messages)
            ai_response = response.choices[0].message.content
        except APIError as e:
            logger.error(f"Azure OpenAI API error: {e.status_code} - {e.message}")
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error from AI service: {e.message}")
        
        await save_message(db, conversation_id, user_id, "user", {"text": user_message})
        await save_message(db, conversation_id, user_id, "assistant", {"text": ai_response})
        await update_conversation_timestamp(db, conversation_id)
        await db.commit()
        
        return ChatResponse(conversation_id=conversation_id, response=ai_response)
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

@app.get("/api/conversations/{conversation_id}")
async def get_conversation_details(
    conversation_id: uuid.UUID,
    current_user: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get conversation details and message history."""
    user_id = uuid.UUID(current_user)
    conversation = await get_conversation(db, conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = await get_message_history(db, conversation_id)
    
    return {
        "conversation": {
            "conversation_id": conversation.conversation_id,
            "user_id": conversation.user_id,
            "title": conversation.title,
            "created_at": conversation.created_at,
        },
        "messages": [
            {
                "id": msg.id,
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            } for msg in messages
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)