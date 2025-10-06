import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, desc, func

from database import ChatbotConversationAudit, ChatbotUserMemory, User
from config import settings
from auth_utils import get_password_hash, verify_password

async def get_or_create_user(db: AsyncSession, user_id: uuid.UUID, email: str = None) -> User:
    """
    Fetches a user by ID or creates a new one if it doesn't exist.
    If a user with the same email already exists, return that user instead.
    """
    # First, try to find user by ID
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if user:
        return user
    
    # If user doesn't exist by ID, check if a user with the same email exists
    if email:
        result = await db.execute(select(User).where(User.email == email))
        existing_user = result.scalar_one_or_none()
        if existing_user:
            return existing_user
    
    # Create new user only if neither ID nor email exists
    user = User(id=user_id, email=email)
    db.add(user)
    await db.flush()  # Flush to make user available in current transaction
    return user

async def ensure_user_exists(user_id: uuid.UUID, email: str = None) -> User:
    """
    Ensures a user exists in the database using a separate connection.
    This function commits the user creation immediately.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    
    # Create a separate engine and session for user creation
    temp_engine = create_async_engine(
        settings.database_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    
    async_session_maker = async_sessionmaker(
        temp_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        # First, try to find user by ID
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        
        if user:
            await temp_engine.dispose()
            return user
        
        # If user doesn't exist by ID, check if a user with the same email exists
        if email:
            result = await session.execute(select(User).where(User.email == email))
            existing_user = result.scalar_one_or_none()
            if existing_user:
                await temp_engine.dispose()
                return existing_user
        
        # Create new user only if neither ID nor email exists
        user = User(id=user_id, email=email)
        session.add(user)
        await session.commit()  # Commit immediately to ensure user is persisted
        
        await temp_engine.dispose()
        return user

async def get_conversation(
    db: AsyncSession, 
    conversation_id: uuid.UUID, 
    user_id: uuid.UUID
) -> Optional[ChatbotConversationAudit]:
    """
    Fetch a conversation record from chatbot_conversation_audit.
    """
    query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id,
        ChatbotConversationAudit.user_id == user_id
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def create_conversation(
    db: AsyncSession, 
    user_id: uuid.UUID, 
    title: Optional[str] = None
) -> ChatbotConversationAudit:
    """
    Create a new conversation record in chatbot_conversation_audit.
    """
    conversation = ChatbotConversationAudit(
        user_id=user_id,
        title=title,
        status='in-progress'
    )
    db.add(conversation)
    await db.flush()
    return conversation

async def update_conversation_timestamp(
    db: AsyncSession, 
    conversation_id: uuid.UUID
) -> None:
    """
    Update the last_message_at timestamp in chatbot_conversation_audit.
    """
    query = update(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id
    ).values(last_message_at=datetime.utcnow())
    
    await db.execute(query)

async def update_conversation_title(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    title: str
) -> None:
    """Update the title of a conversation."""
    query = update(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id
    ).values(title=title)
    await db.execute(query)

async def get_message_history(
    db: AsyncSession, 
    conversation_id: uuid.UUID, 
    limit: int = 20
) -> List[ChatbotUserMemory]:
    """
    Fetch recent message records from chatbot_user_memory.
    """
    query = select(ChatbotUserMemory).where(
        ChatbotUserMemory.conversation_id == conversation_id
    ).order_by(ChatbotUserMemory.created_at.asc()).limit(limit)
    
    result = await db.execute(query)
    return result.scalars().all()

async def save_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    content: Dict[str, Any]
) -> ChatbotUserMemory:
    """
    Save a new message record to chatbot_user_memory.
    """
    message = ChatbotUserMemory(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content
    )
    db.add(message)
    await db.flush()
    return message

async def update_conversation_summary(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    summary: str,
    model: Optional[str] = None,
    token_usage: Optional[Dict[str, Any]] = None
) -> None:
    """
    Update conversation summary and related metadata.
    """
    update_data = {"conversation_summary": summary}
    if model:
        update_data["model"] = model
    if token_usage:
        update_data["token_usage"] = token_usage
    
    query = update(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id
    ).values(**update_data)
    
    await db.execute(query)

async def increment_conversation_token_usage(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    usage_delta: Dict[str, int],
    model: Optional[str] = None,
) -> None:
    """
    Increment the conversation's cumulative token_usage JSONB by the provided delta.

    The JSON structure maintained is a simple cumulative counter:
    {
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int
    }
    """
    # Fetch existing token_usage
    result = await db.execute(
        select(ChatbotConversationAudit.token_usage).where(
            ChatbotConversationAudit.conversation_id == conversation_id
        )
    )
    current_usage: Optional[Dict[str, int]] = result.scalar_one_or_none()

    # Initialize if missing
    if not isinstance(current_usage, dict):
        current_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Safely add deltas
    new_usage = {
        "prompt_tokens": int(current_usage.get("prompt_tokens", 0) or 0) + int(usage_delta.get("prompt_tokens", 0) or 0),
        "completion_tokens": int(current_usage.get("completion_tokens", 0) or 0) + int(usage_delta.get("completion_tokens", 0) or 0),
        "total_tokens": int(current_usage.get("total_tokens", 0) or 0) + int(usage_delta.get("total_tokens", 0) or 0),
    }

    update_data: Dict[str, Any] = {"token_usage": new_usage}
    if model:
        update_data["model"] = model

    query = update(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id
    ).values(**update_data)

    await db.execute(query)

async def get_conversations_to_summarize(db: AsyncSession) -> List[ChatbotConversationAudit]:
    """
    Finds conversations that need summarization (started 15+ minutes ago).
    A conversation is considered ready for summarization if it was created more than 15 minutes ago
    and does not yet have a summary.
    """
    fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)
    
    query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_summary.is_(None),
        ChatbotConversationAudit.created_at < fifteen_minutes_ago,
        ChatbotConversationAudit.status.in_(['active', 'in-progress'])
    )
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_conversations_to_summarize_by_user_inactivity(db: AsyncSession, user_id: uuid.UUID) -> List[ChatbotConversationAudit]:
    """
    Finds conversations for a specific user that need summarization based on user inactivity.
    A conversation is considered ready for summarization if:
    1. The user has been inactive for 15+ minutes (no new messages)
    2. The conversation doesn't have a summary yet
    3. The conversation is still active/in-progress
    """
    fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)
    
    # First, find the user's last message time
    last_message_query = select(func.max(ChatbotUserMemory.created_at)).where(
        ChatbotUserMemory.user_id == user_id
    )
    last_message_result = await db.execute(last_message_query)
    last_message_time = last_message_result.scalar()
    
    # If user has no messages or last message was more than 15 minutes ago
    if last_message_time is None or last_message_time < fifteen_minutes_ago:
        query = select(ChatbotConversationAudit).where(
            ChatbotConversationAudit.user_id == user_id,
            ChatbotConversationAudit.conversation_summary.is_(None),
            ChatbotConversationAudit.status.in_(['active', 'in-progress'])
        )
        
        result = await db.execute(query)
        return result.scalars().all()
    
    return []

async def get_user_inactivity_status(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """
    Get the inactivity status of a specific user.
    Returns information about when the user was last active and if they should be summarized.
    """
    fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)
    
    # Get user's last message time
    last_message_query = select(func.max(ChatbotUserMemory.created_at)).where(
        ChatbotUserMemory.user_id == user_id
    )
    last_message_result = await db.execute(last_message_query)
    last_message_time = last_message_result.scalar()
    
    # Get user's active conversations
    active_conversations_query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.user_id == user_id,
        ChatbotConversationAudit.status.in_(['active', 'in-progress'])
    )
    active_result = await db.execute(active_conversations_query)
    active_conversations = active_result.scalars().all()
    
    # Check if user is inactive
    is_inactive = last_message_time is None or last_message_time < fifteen_minutes_ago
    
    # Get conversations that need summarization
    conversations_to_summarize = await get_conversations_to_summarize_by_user_inactivity(db, user_id)
    
    return {
        "user_id": str(user_id),
        "last_message_time": last_message_time.isoformat() if last_message_time else None,
        "is_inactive": is_inactive,
        "inactivity_duration_minutes": (datetime.utcnow() - last_message_time).total_seconds() / 60 if last_message_time else None,
        "active_conversations": len(active_conversations),
        "conversations_to_summarize": len(conversations_to_summarize),
        "should_summarize": len(conversations_to_summarize) > 0
    }

async def get_latest_summary_for_user(
    db: AsyncSession, 
    user_id: uuid.UUID
) -> Optional[str]:
    """
    Fetch the most recent non-null conversation summary for a user.
    """
    query = select(ChatbotConversationAudit.conversation_summary).where(
        ChatbotConversationAudit.user_id == user_id,
        ChatbotConversationAudit.conversation_summary.isnot(None)
    ).order_by(desc(ChatbotConversationAudit.created_at)).limit(1)
    
    result = await db.execute(query)
    summary = result.scalar_one_or_none()
    return summary

async def get_recent_user_messages(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 10,
) -> List[str]:
    """Fetch the most recent raw user message texts across conversations.

    Returns newest first, up to `limit` items. Only extracts the 'text' field
    when content is a dict; otherwise uses string representation.
    """
    query = select(ChatbotUserMemory).where(
        ChatbotUserMemory.user_id == user_id,
        ChatbotUserMemory.role == "user",
    ).order_by(desc(ChatbotUserMemory.created_at)).limit(limit)

    result = await db.execute(query)
    rows: List[ChatbotUserMemory] = result.scalars().all()
    messages: List[str] = []
    for row in rows:
        try:
            if isinstance(row.content, dict):
                text_val = row.content.get("text", "")
            else:
                text_val = str(row.content)
            text_val = (text_val or "").strip()
            if text_val:
                messages.append(text_val)
        except Exception:
            continue
    return messages

async def update_conversation_status(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    new_status: str
) -> None:
    """
    Update the status of a conversation.
    Valid statuses: 'active', 'in-progress', 'archived'
    """
    valid_statuses = ['active', 'in-progress', 'archived']
    if new_status not in valid_statuses:
        raise ValueError(f"Invalid status: {new_status}. Must be one of {valid_statuses}")
    
    query = update(ChatbotConversationAudit).where(
        ChatbotConversationAudit.conversation_id == conversation_id
    ).values(status=new_status)
    
    await db.execute(query)

async def get_conversations_by_status(
    db: AsyncSession,
    user_id: uuid.UUID,
    status: str
) -> List[ChatbotConversationAudit]:
    """
    Get all conversations for a user with a specific status.
    """
    query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.user_id == user_id,
        ChatbotConversationAudit.status == status
    ).order_by(desc(ChatbotConversationAudit.created_at))
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_conversations_to_archive(db: AsyncSession) -> List[ChatbotConversationAudit]:
    """
    Find conversations that should be archived and summarized (inactive for 15+ minutes, no summary yet).
    """
    fifteen_minutes_ago = datetime.utcnow() - timedelta(minutes=15)
    
    query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.status.in_(['active', 'in-progress']),
        ChatbotConversationAudit.last_message_at < fifteen_minutes_ago,
        ChatbotConversationAudit.conversation_summary.is_(None)  # Only conversations without summaries
    )
    
    result = await db.execute(query)
    return result.scalars().all()

async def get_cumulative_summary_context(
    db: AsyncSession,
    user_id: uuid.UUID
) -> str:
    """
    Get cumulative summary context from all previous conversations for a user.
    Returns formatted context string for use in AI prompts.
    This creates a growing memory that builds upon previous conversations.
    """
    query = select(ChatbotConversationAudit).where(
        ChatbotConversationAudit.user_id == user_id,
        ChatbotConversationAudit.conversation_summary is not None
    ).order_by(ChatbotConversationAudit.created_at.asc())
    
    result = await db.execute(query)
    conversations = result.scalars().all()
    
    if not conversations:
        return "No previous conversation history available."
    
    # Create cumulative context that builds upon previous conversations
    context_parts = []
    context_parts.append(f"User has had {len(conversations)} previous conversations. Here's the cumulative memory:")
    
    for i, conv in enumerate(conversations, 1):
        context_parts.append(f"Conversation {i} (from {conv.created_at.strftime('%Y-%m-%d')}): {conv.conversation_summary}")
    
    # Add a note about the cumulative nature
    context_parts.append(f"This is conversation #{len(conversations) + 1} for this user. Use the above context to provide personalized, continuous care.")
    
    return "\n\n".join(context_parts)


# Authentication CRUD Operations
async def create_user(
    db: AsyncSession, 
    email: str, 
    password: str,
    first_name: str = None,
    last_name: str = None,
    display_name: str = None,
    phone_number: str = None,
    is_caregiver: bool = False
) -> User:
    """
    Create a new user with hashed password.
    """
    # Check if user already exists
    existing_user = await get_user_by_email(db, email)
    if existing_user:
        raise ValueError("User with this email already exists")
    
    # Hash the password
    hashed_password = get_password_hash(password)
    
    # Generate display name if not provided
    if not display_name and first_name and last_name:
        display_name = f"{first_name} {last_name}"
    elif not display_name and first_name:
        display_name = first_name
    
    # Create new user
    user = User(
        email=email,
        password_hash=hashed_password,
        first_name=first_name,
        last_name=last_name,
        display_name=display_name,
        phone_number=phone_number,
        is_caregiver=is_caregiver,
        auth_provider="email",
        onboarding_completed=False,
        onboarding_current_step=0,
        care_receivers_count=0,
        phone_verified=False
    )
    
    db.add(user)
    await db.flush()
    return user

async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """
    Get user by email address.
    """
    query = select(User).where(User.email == email)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_display_name(db: AsyncSession, display_name: str) -> Optional[User]:
    """
    Get user by display name.
    """
    query = select(User).where(User.display_name == display_name)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    """
    Get user by ID.
    """
    query = select(User).where(User.id == user_id)
    result = await db.execute(query)
    return result.scalar_one_or_none()

async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """
    Authenticate user with email and password.
    """
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not user.password_hash or not verify_password(password, user.password_hash):
        return None
    return user

async def update_user_last_login(db: AsyncSession, user_id: uuid.UUID) -> None:
    """
    Update user's last login timestamp.
    """
    query = update(User).where(User.id == user_id).values(
        last_login_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    await db.execute(query)

async def update_user_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    first_name: str = None,
    last_name: str = None,
    display_name: str = None,
    avatar: str = None,
    phone_number: str = None,
    is_caregiver: bool = None,
    preferences: Dict[str, Any] = None
) -> Optional[User]:
    """
    Update user profile information.
    """
    update_data = {"updated_at": datetime.utcnow()}
    
    if first_name is not None:
        update_data["first_name"] = first_name
    if last_name is not None:
        update_data["last_name"] = last_name
    if display_name is not None:
        update_data["display_name"] = display_name
    if avatar is not None:
        update_data["avatar"] = avatar
    if phone_number is not None:
        update_data["phone_number"] = phone_number
    if is_caregiver is not None:
        update_data["is_caregiver"] = is_caregiver
    if preferences is not None:
        update_data["preferences"] = preferences
    
    if len(update_data) <= 1:  # Only updated_at
        return None
    
    query = update(User).where(User.id == user_id).values(**update_data)
    await db.execute(query)
    
    # Return updated user
    return await get_user_by_id(db, user_id)

async def update_onboarding_progress(
    db: AsyncSession,
    user_id: uuid.UUID,
    current_step: int,
    completed: bool = False
) -> None:
    """
    Update user's onboarding progress.
    """
    update_data = {
        "onboarding_current_step": current_step,
        "updated_at": datetime.utcnow()
    }
    
    if completed:
        update_data["onboarding_completed"] = True
    
    query = update(User).where(User.id == user_id).values(**update_data)
    await db.execute(query)


