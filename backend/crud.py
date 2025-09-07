"""
CRUD (Create, Read, Update, Delete) operations for the database.
Corrected to use the final database schema.
"""

import uuid
from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from models import User, Conversation, ChatbotUserMemory


async def get_or_create_user(db: AsyncSession, user_id: uuid.UUID) -> User:
    """Fetches a user by their ID or creates one if it doesn't exist."""
    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalars().first()
    
    if not user:
        print(f"User with ID {user_id} not found. Creating a new user entry.")
        placeholder_email = f"dev-user-{user_id}@example.com"
        user = User(id=user_id, email=placeholder_email)
        db.add(user)
        await db.flush() 
    return user


async def get_conversation(db: AsyncSession, conversation_id: uuid.UUID, user_id: uuid.UUID) -> Conversation | None:
    """Gets a conversation by its ID, ensuring it belongs to the user."""
    result = await db.execute(
        select(Conversation).filter_by(conversation_id=conversation_id, user_id=user_id)
    )
    return result.scalars().first()


async def create_conversation(db: AsyncSession, user_id: uuid.UUID, title: str) -> Conversation:
    """Creates a new conversation for a user."""
    new_conversation = Conversation(user_id=user_id, title=title, status="active")
    db.add(new_conversation)
    await db.flush() 
    return new_conversation


async def update_conversation_timestamp(db: AsyncSession, conversation_id: uuid.UUID):
    """Updates the last_message_at timestamp for a conversation."""
    result = await db.execute(
        select(Conversation).filter_by(conversation_id=conversation_id)
    )
    conversation = result.scalars().first()
    if conversation:
        conversation.last_message_at = datetime.utcnow()
        await db.flush()


async def get_message_history(db: AsyncSession, conversation_id: uuid.UUID) -> List[ChatbotUserMemory]:
    """Gets all messages for a conversation, ordered by creation time."""
    result = await db.execute(
        select(ChatbotUserMemory)
        .filter_by(conversation_id=conversation_id)
        .order_by(ChatbotUserMemory.created_at)
    )
    return result.scalars().all()


async def save_message(
    db: AsyncSession,
    conversation_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    content: Dict[str, Any]
):
    """Saves a user or assistant message to the database."""
    new_message = ChatbotUserMemory(
        conversation_id=conversation_id,
        user_id=user_id,
        role=role,
        content=content
    )
    db.add(new_message)
    await db.flush()