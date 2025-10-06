"""
FastAPI application with a multi-agent orchestrator for the core chat endpoint.
"""
import uuid
import asyncio
from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from contextlib import asynccontextmanager
import logging

from database import get_db, init_database, close_database
from schemas import (
    ChatRequest, ChatResponse, HealthResponse, 
    UserRegister, UserLogin, TokenResponse, UserProfile, UserUpdate
)
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
    get_conversations_by_status,
    increment_conversation_token_usage,
    update_conversation_title,
    # Authentication CRUD operations
    create_user,
    get_user_by_id,
    authenticate_user,
    update_user_last_login,
    update_user_profile,
    update_onboarding_progress
)
from config import settings
# Import the new agents
from agents import core_chat_agent, personalizer_agent, summarizer_agent
# Import background summarization service
from summarization_service import start_summarization_service, stop_summarization_service
# Import authentication utilities
from auth_utils import get_user_id_from_token, create_token_response

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
    
    try:
        import vertexai
        vertexai.init(project=settings.vertex_project_id, location=settings.vertex_location)
        logger.info("Vertex AI initialized")
    except Exception as e:
        logger.warning(f"Vertex AI init skipped/failed: {e}")
    
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

# --- Simple public chatbot alias for Flutter integration ---
from pydantic import BaseModel

class SimpleChatbotRequest(BaseModel):
    message: str
    history: list[str] | None = None

@app.post("/api/chatbot/reply")
async def simple_chatbot_reply(req: SimpleChatbotRequest):
    try:
        history = []
        if req.history:
            # Map plain string history into role/content pairs for the agent
            for i, text in enumerate(req.history):
                role = "user" if i % 2 == 0 else "assistant"
                history.append({"role": role, "content": text})
        ai_response, _usage, _model = await core_chat_agent(
            history=history,
            user_message=req.message,
            cumulative_context=None,
            suppress_greeting=True,
        )
        return {"reply": ai_response}
    except Exception as e:
        logger.error(f"/api/chatbot/reply error: {e}", exc_info=True)
        raise HTTPException(status_code=502, detail="AI generation failed")

# --- Development User ID & Email ---
# For development, we use fixed user details to simulate a single returning user.
DEV_USER_ID = str(uuid.uuid4())
DEV_USER_EMAIL = "dev.user@example.com" # ADDED
logger.info(f"Using fixed development user ID: {DEV_USER_ID}")

async def get_current_user(
    request: Request,
    auth_credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """Authentication dependency. Validates JWT token and returns user details."""
    try:
        # Prefer application JWT from X-User-Token when present (Cloud Run ID token is in Authorization)
        user_token_header = request.headers.get("x-user-token") or request.headers.get("X-User-Token")
        token: str | None = None
        if user_token_header:
            token = user_token_header.split(" ", 1)[1] if user_token_header.lower().startswith("bearer ") else user_token_header
        elif auth_credentials is not None:
            # Fall back to Authorization bearer if provided (e.g., server-to-server app token)
            token = auth_credentials.credentials
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization token is missing",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Get user ID from token
        user_id = get_user_id_from_token(token)
        
        # Get user from database
        user = await get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Treat users as active by default if the attribute is missing
        is_active = getattr(user, "is_active", True)
        if not is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is deactivated",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        return {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Authentication error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

# --- API Endpoints ---
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy")

# --- Authentication Endpoints ---
@app.post("/api/auth/register", response_model=TokenResponse)
async def register_user(
    user_data: UserRegister,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    try:
        # Create new user
        user = await create_user(
            db=db,
            email=user_data.email,
            password=user_data.password,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            display_name=user_data.display_name,
            phone_number=user_data.phone_number,
            is_caregiver=user_data.is_caregiver
        )
        
        # Commit the user creation
        await db.commit()
        
        # Create token response
        token_response = create_token_response(user.id, user.display_name or user.email)
        
        logger.info(f"New user registered: {user.email} ({user.display_name})")
        return TokenResponse(**token_response)
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )

@app.post("/api/auth/login", response_model=TokenResponse)
async def login_user(
    login_data: UserLogin,
    db: AsyncSession = Depends(get_db)
):
    """Login user and return JWT token."""
    try:
        # Authenticate user
        user = await authenticate_user(db, login_data.email, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Update last login
        await update_user_last_login(db, user.id)
        await db.commit()
        
        # Create token response
        token_response = create_token_response(user.id, user.display_name or user.email)
        
        logger.info(f"User logged in: {user.email} ({user.display_name})")
        return TokenResponse(**token_response)
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        logger.error(f"Login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )

@app.get("/api/auth/me", response_model=UserProfile)
async def get_current_user_profile(
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's profile."""
    try:
        user_id = uuid.UUID(user_info["id"])
        user = await get_user_by_id(db, user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return UserProfile(
            id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            display_name=user.display_name,
            avatar=user.avatar,
            phone_number=user.phone_number,
            phone_verified=user.phone_verified,
            is_caregiver=user.is_caregiver,
            care_receivers_count=user.care_receivers_count,
            onboarding_completed=user.onboarding_completed,
            onboarding_current_step=user.onboarding_current_step,
            created_at=user.created_at,
            last_login_at=user.last_login_at,
            updated_at=user.updated_at
        )
        
    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch profile"
        )

@app.put("/api/auth/profile", response_model=UserProfile)
async def update_user_profile_endpoint(
    profile_data: UserUpdate,
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile."""
    try:
        user_id = uuid.UUID(user_info["id"])
        
        # Update profile
        updated_user = await update_user_profile(
            db, 
            user_id,
            first_name=profile_data.first_name,
            last_name=profile_data.last_name,
            display_name=profile_data.display_name,
            avatar=profile_data.avatar,
            phone_number=profile_data.phone_number,
            is_caregiver=profile_data.is_caregiver,
            preferences=profile_data.preferences
        )
        await db.commit()
        
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No changes provided"
            )
        
        return UserProfile(
            id=updated_user.id,
            email=updated_user.email,
            first_name=updated_user.first_name,
            last_name=updated_user.last_name,
            display_name=updated_user.display_name,
            avatar=updated_user.avatar,
            phone_number=updated_user.phone_number,
            phone_verified=updated_user.phone_verified,
            is_caregiver=updated_user.is_caregiver,
            care_receivers_count=updated_user.care_receivers_count,
            onboarding_completed=updated_user.onboarding_completed,
            onboarding_current_step=updated_user.onboarding_current_step,
            created_at=updated_user.created_at,
            last_login_at=updated_user.last_login_at,
            updated_at=updated_user.updated_at
        )
        
    except ValueError as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        await db.rollback()
        logger.error(f"Profile update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profile update failed"
        )

@app.post("/api/ai/start-conversation", response_model=ChatResponse)
async def start_conversation(
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Starts a new conversation and returns a personalized greeting.
    The frontend should call this endpoint to begin a new chat session.
    """
    try:
        user_id = uuid.UUID(user_info["id"])
        user_email = user_info["email"]
        
        # Ensure user exists in the database
        user = await get_or_create_user(db, user_id=user_id, email=user_email)
        await db.commit()
        user_id = user.id

        # 1. Get long-term memory for personalization
        cumulative_context = await get_cumulative_summary_context(db, user_id)
        
        # 2. Call the appropriate agent for the greeting (with recent phrases)
        from crud import get_recent_user_messages, get_latest_summary_for_user
        recent_phrases = await get_recent_user_messages(db, user_id, limit=5)
        latest_summary = await get_latest_summary_for_user(db, user_id)
        if cumulative_context and cumulative_context != "No previous conversation history available.":
            # For returning users, use the personalizer_agent for a warm greeting
            initial_greeting, usage, model_name = await personalizer_agent(
                cumulative_context,
                first_name=user.display_name or user.email,
                recent_user_phrases=recent_phrases,
                latest_summary=latest_summary,
            )
        else:
            # For new users, get a generic but friendly opening from the core agent
            initial_greeting, usage, model_name = await core_chat_agent(
                history=[],
                user_message="Hello", # A neutral starting point
                cumulative_context=cumulative_context,
                suppress_greeting=False,
                first_name=user.display_name or user.email
            )
            
        # 3. Create a new conversation in the database
        title = initial_greeting[:60]
        conversation = await create_conversation(db, user_id, title)
        await update_conversation_status(db, conversation.conversation_id, "active")

        # 4. Save the AI's greeting as the first message
        await save_message(db, conversation.conversation_id, user_id, "assistant", {"text": initial_greeting})
        await update_conversation_timestamp(db, conversation.conversation_id)
        # Record token usage and model
        await increment_conversation_token_usage(db, conversation.conversation_id, usage, model_name)

        await db.commit()

        # 5. Return the new conversation ID and the greeting
        return ChatResponse(conversation_id=conversation.conversation_id, response=initial_greeting)

    except Exception as e:
        logger.error(f"Error in start_conversation endpoint: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=500, detail="Could not start a new conversation.")

# ==============================================================================
# === MODIFIED: CHAT ENDPOINT NOW ONLY HANDLES ONGOING CONVERSATIONS ===
# ==============================================================================
@app.post("/api/ai/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Handles ongoing chat messages within an existing conversation.
    A conversation_id is now REQUIRED.
    """
    try:
        user_id = uuid.UUID(user_info["id"])
        conversation_id = request.conversation_id
        user_message = request.message
        
        if not conversation_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="conversation_id is required. Please start a new conversation using the /api/ai/start-conversation endpoint first."
            )

        # 1. Get the existing conversation
        conversation = await get_conversation(db, conversation_id, user_id)
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

        # 2. Get history and context
        cumulative_context = await get_cumulative_summary_context(db, user_id)
        message_history = await get_message_history(db, conversation_id)
        formatted_history = [
            {
                "role": msg.role,
                "content": msg.content.get('text', str(msg.content))
            }
            for msg in message_history
        ]

        # 3. Call the Core Chat Agent, always suppressing the greeting
        ai_response, usage, model_name = await core_chat_agent(
            history=formatted_history,
            user_message=user_message,
            cumulative_context=cumulative_context,
            suppress_greeting=True, # This prevents repeated greetings
        )

        # 4. Save messages and commit
        await save_message(db, conversation_id, user_id, "user", {"text": user_message})
        await save_message(db, conversation_id, user_id, "assistant", {"text": ai_response})
        await update_conversation_timestamp(db, conversation_id)
        await update_conversation_status(db, conversation_id, "in-progress")
        # Record token usage and model
        await increment_conversation_token_usage(db, conversation_id, usage, model_name)

        await db.commit()
        
        return ChatResponse(conversation_id=conversation_id, response=ai_response)
        
    except Exception as e:
        logger.error(f"AI service error: {e}")
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Error from AI service")
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        logger.error(f"Unexpected error in chat endpoint: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred.")


@app.put("/api/auth/onboarding")
async def update_onboarding_progress_endpoint(
    current_step: int,
    completed: bool = False,
    user_info: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user's onboarding progress."""
    try:
        user_id = uuid.UUID(user_info["id"])
        
        await update_onboarding_progress(db, user_id, current_step, completed)
        await db.commit()
        
        return {"message": "Onboarding progress updated successfully"}
        
    except Exception as e:
        await db.rollback()
        logger.error(f"Onboarding update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Onboarding update failed"
        )

## Removing corrupted duplicate chat endpoint block below; the valid chat endpoint is defined earlier

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


