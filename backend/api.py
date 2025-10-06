"""
API entrypoint that reuses the existing FastAPI app from main and adds a
simple `/chat` endpoint for Flutter, plus a root health route.

This module exposes `app` so the Dockerfile can run `uvicorn api:app`.
"""

from typing import Dict
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from dotenv import load_dotenv

# Reuse existing application, dependencies, schemas, and logic
from main import app as main_app, get_current_user  # type: ignore
from database import get_db
from schemas import ChatRequest, ChatResponse
from crud import (
    get_conversation,
    get_message_history,
    save_message,
    update_conversation_timestamp,
    update_conversation_status,
    increment_conversation_token_usage,
    get_cumulative_summary_context,
)
from agents import core_chat_agent


# Load environment variables from .env if present
load_dotenv()

router = APIRouter()


@router.get("/")
async def root() -> Dict[str, str]:
    return {"status": "ok"}


@router.post("/chat", response_model=ChatResponse)
async def handle_chat(
    request: ChatRequest,
    user_info: Dict[str, str] = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    A simplified chat endpoint for Flutter that reuses the existing
    multi-agent chat flow. Requires an existing conversation_id.
    """
    try:
        user_id = uuid.UUID(user_info["id"])

        if not request.conversation_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "conversation_id is required. Start a conversation via "
                    "/api/ai/start-conversation first."
                ),
            )

        # Fetch conversation and history
        conversation = await get_conversation(db, request.conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")

        cumulative_context = await get_cumulative_summary_context(db, user_id)
    message_history = await get_message_history(db, request.conversation_id)
    formatted_history = [
        {
            "role": msg.role,
            "content": msg.content.get('text', str(msg.content)),
        }
        for msg in message_history
    ]

        # Call the core chat agent without greetings
        ai_response, usage, model_name = await core_chat_agent(
            history=formatted_history,
            user_message=request.message,
            cumulative_context=cumulative_context,
            suppress_greeting=True,
        )

        # Persist user and assistant messages and update conversation
        await save_message(db, request.conversation_id, user_id, "user", {"text": request.message})
        await save_message(db, request.conversation_id, user_id, "assistant", {"text": ai_response})
        await update_conversation_timestamp(db, request.conversation_id)
        await update_conversation_status(db, request.conversation_id, "in-progress")
        await increment_conversation_token_usage(db, request.conversation_id, usage, model_name)
        await db.commit()

        return ChatResponse(conversation_id=request.conversation_id, response=ai_response)

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        # Keep details out of the response for safety; log server-side if needed
        raise HTTPException(status_code=500, detail="Internal Server Error") from e


# Re-export the main app and attach our lightweight router
app = main_app
app.include_router(router)


