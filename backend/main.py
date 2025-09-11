"""
FastAPI application with a multi-agent orchestrator for the core chat endpoint.
"""
import uuid
import asyncio
from fastapi import FastAPI, Depends, HTTPException, status
from typing import Optional
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
    save_message,
    get_latest_summary_for_user,
    update_conversation_summary,
    update_conversation_status,
    get_conversations_to_archive,
    get_cumulative_summary_context,
    get_user_inactivity_status,
    get_conversations_to_summarize_by_user_inactivity,
    get_conversations_by_status  # Ensure this is imported if used
)
from config import settings
# Import the new agents
from agents import core_chat_agent, personalizer_agent, summarizer_agent
# Import background summarization service
from summarization_service import start_summarization_service, stop_summarization_service

# --- Basic Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
app_state = {}

# --- Application Lifespan (Startup/Shutdown) ---
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
    
    # Start background summarization service
    logger.info("Starting background summarization service...")
    summarization_task = asyncio.create_task(start_summarization_service())
    app_state["summarization_task"] = summarization_task
    logger.info("Background summarization service started successfully")
    
    yield
    
    logger.info("Application shutdown...")
    # Stop background summarization service
    if "summarization_task" in app_state:
        logger.info("Stopping background summarization service...")
        app_state["summarization_task"].cancel()
        try:
            await app_state["summarization_task"]
        except asyncio.CancelledError:
            pass
    
    await close_database()
    logger.info("Application shutdown complete")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="Conversational AI Backend",
    description="A multi-agent backend for a conversational AI application.",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Development User ID & Email ---
# For development, we use fixed user details to simulate a single returning user.
DEV_USER_ID = str(uuid.uuid4())
DEV_USER_EMAIL = "dev.user@example.com" # ADDED
logger.info(f"Using fixed development user ID: {DEV_USER_ID}")

def get_current_user() -> dict:
    """Authentication dependency. Returns a dict with fixed user details for development."""
    # For development, always return the dev user
    # In production, you would validate the token and return user details
    return {"id": DEV_USER_ID, "email": DEV_USER_EMAIL}

# --- API Endpoints ---
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")

@app.post("/api/ai/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_info: dict = Depends(get_current_user), # CHANGED
    db: AsyncSession = Depends(get_db)
):
    """
    Main chat endpoint that acts as an orchestrator, directing requests to the appropriate AI agent.
    """
    try:
        # Unpack user details from the dictionary
        user_id = uuid.UUID(user_info["id"]) # CHANGED
        user_email = user_info["email"] # ADDED
        
        conversation_id = request.conversation_id
        user_message = request.message
        
        # Ensure user exists in database using current session
        user = await get_or_create_user(db, user_id=user_id, email=user_email)
        logger.info(f"User created/found: {user.id} with email: {user.email}")
        
        # Ensure we're using the correct user_id from the created/found user
        user_id = user.id
        
        # Commit the user creation to ensure it's available for foreign key constraints
        await db.commit()
        
        # --- ORCHESTRATOR LOGIC ---
        # Get cumulative context for all agents
        cumulative_context = await get_cumulative_summary_context(db, user_id)
        
        if conversation_id:
            # --- FLOW 1: CONTINUING AN EXISTING CONVERSATION ---
            conversation = await get_conversation(db, conversation_id, user_id)
            if not conversation:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

            # Update status to in-progress for ongoing conversation
            await update_conversation_status(db, conversation_id, "in-progress")

            message_history = await get_message_history(db, conversation_id)
            formatted_history = [{"role": msg.role, "content": msg.content.get("text", str(msg.content))} for msg in message_history]

            # Call the Core Chat Agent with cumulative context
            ai_response = await core_chat_agent(formatted_history, user_message, cumulative_context)
        
        else:
            # --- FLOW 2: STARTING A NEW CONVERSATION ---
            title = user_message[:60]
            conversation = await create_conversation(db, user_id, title)
            conversation_id = conversation.conversation_id
            
            # Set status to active for new conversation
            await update_conversation_status(db, conversation_id, "active")
            
            initial_greeting = ""
            if cumulative_context != "No previous conversation history available.":
                # If cumulative context exists, call the Personalizer Agent
                initial_greeting = await personalizer_agent(cumulative_context)

            # Call the Core Chat Agent with cumulative context
            follow_up_response = await core_chat_agent([], user_message, cumulative_context)

            # Combine the greeting and the response
            ai_response = f"{initial_greeting}\n\n{follow_up_response}" if initial_greeting else follow_up_response

        # --- Save messages and commit to database ---
        await save_message(db, conversation_id, user_id, "user", {"text": user_message})
        await save_message(db, conversation_id, user_id, "assistant", {"text": ai_response})
        await update_conversation_timestamp(db, conversation_id)
        
        # --- Hybrid Summarization Approach ---
        # For active conversations, we don't summarize immediately
        # Summaries will be generated by background job after 15 minutes of inactivity
        # This is more efficient and provides better context for finished conversations
        
        await db.commit()
        
        return ChatResponse(conversation_id=conversation_id, response=ai_response)
        
    except APIError as e:
        logger.error(f"Azure OpenAI API error: {e.status_code} - {e.message}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Error from AI service: {e.message}")
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")

# Note: The get_conversation_details endpoint would also need the multi-agent logic
# if you want it to behave similarly, but for now it remains as a simple history fetcher.
@app.get("/api/conversations/{conversation_id}")
async def get_conversation_details(
    conversation_id: uuid.UUID,
    user_info: dict = Depends(get_current_user), # CHANGED
    db: AsyncSession = Depends(get_db)
):
    """Get conversation details and message history."""
    user_id = uuid.UUID(user_info["id"]) # CHANGED
    conversation = await get_conversation(db, conversation_id, user_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    messages = await get_message_history(db, conversation_id)
    
    # This can be expanded to return more summary details later
    return {
        "conversation": { 
            "conversation_id": conversation.conversation_id, 
            "title": conversation.title,
            "conversation_summary": conversation.conversation_summary,
            "last_message_at": conversation.last_message_at
        },
        "messages": [
            { "id": msg.message_id, "role": msg.role, "content": msg.content } for msg in messages
        ]
    }

@app.post("/api/admin/summarize-pending")
async def manually_trigger_summarization():
    """Manually trigger summarization of pending conversations (for testing)."""
    try:
        from summarization_service import summarization_service
        await summarization_service.process_pending_summaries()
        return {"message": "Summarization process completed successfully"}
    except Exception as e:
        logger.error(f"Error in manual summarization: {e}")
        raise HTTPException(status_code=500, detail=f"Summarization failed: {str(e)}")

@app.get("/api/conversations/status/{status}")
async def get_conversations_by_status_endpoint(
    status: str,
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get conversations by status for a user."""
    try:
        user_id = uuid.UUID(user_info["id"])
        conversations = await get_conversations_by_status(db, user_id, status)
        
        return {
            "status": status,
            "count": len(conversations),
            "conversations": [
                {
                    "conversation_id": str(conv.conversation_id),
                    "title": conv.title,
                    "status": conv.status,
                    "created_at": conv.created_at.isoformat(),
                    "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
                    "has_summary": conv.conversation_summary is not None
                }
                for conv in conversations
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid status: {e}")
    except Exception as e:
        logger.error(f"Error getting conversations by status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get conversations")

@app.post("/api/conversations/{conversation_id}/status")
async def update_conversation_status_endpoint(
    conversation_id: str,
    new_status: str,
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update the status of a conversation."""
    try:
        user_id = uuid.UUID(user_info["id"])
        conv_id = uuid.UUID(conversation_id)
        
        # Verify the conversation belongs to the user
        conversation = await get_conversation(db, conv_id, user_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        await update_conversation_status(db, conv_id, new_status)
        await db.commit()
        
        return {"message": f"Conversation status updated to {new_status}"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {e}")
    except Exception as e:
        logger.error(f"Error updating conversation status: {e}")
        raise HTTPException(status_code=500, detail="Failed to update conversation status")

@app.get("/api/user/inactivity-status")
async def get_user_inactivity_status_endpoint(
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get the inactivity status of the current user."""
    try:
        user_id = uuid.UUID(user_info["id"])
        status = await get_user_inactivity_status(db, user_id)
        return status
    except Exception as e:
        logger.error(f"Error getting user inactivity status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get user inactivity status")

@app.post("/api/user/summarize-inactive")
async def summarize_user_inactive_conversations(
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Summarize inactive conversations for the current user."""
    try:
        user_id = uuid.UUID(user_info["id"])
        
        # Get conversations that need summarization for this user
        conversations = await get_conversations_to_summarize_by_user_inactivity(db, user_id)
        
        if not conversations:
            return {"message": "No conversations need summarization for this user"}
        
        # Summarize each conversation
        from summarization_service import summarization_service
        for conversation in conversations:
            try:
                await summarization_service.summarize_conversation(db, conversation)
            except Exception as e:
                logger.error(f"Failed to summarize conversation {conversation.conversation_id}: {e}")
                continue
        
        await db.commit()
        
        return {
            "message": f"Successfully processed {len(conversations)} conversations for summarization",
            "conversations_processed": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error summarizing user conversations: {e}")
        raise HTTPException(status_code=500, detail="Failed to summarize user conversations")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)