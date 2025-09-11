"""
SQLAlchemy models and async database session setup for the conversational AI application.
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
import uuid

Base = declarative_base()


class User(Base):
    """Model for users table."""
    
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=True)  # Optional email field
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Relationship to conversations
    conversations = relationship("ChatbotConversationAudit", back_populates="user")


class ChatbotConversationAudit(Base):
    """Model for chatbot_conversation_audit table."""
    
    __tablename__ = "chatbot_conversation_audit"
    
    conversation_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(Text, nullable=True)
    conversation_summary = Column(Text, nullable=True)
    model = Column(Text, nullable=True)
    token_usage = Column(JSONB, nullable=True)
    status = Column(Text, nullable=False, default='in-progress')
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    archived = Column(Boolean, nullable=False, default=False)
    
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("ChatbotUserMemory", back_populates="conversation")


class ChatbotUserMemory(Base):
    """Model for chatbot_user_memory table."""
    
    __tablename__ = "chatbot_user_memory"
    
    message_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("chatbot_conversation_audit.conversation_id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(Text, nullable=False)
    content = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())
    
    # Add check constraint for role
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name='check_role'),
    )
    
    # Relationships
    user = relationship("User")
    conversation = relationship("ChatbotConversationAudit", back_populates="messages")


# Database engine and session setup
engine = None
async_session_maker = None


async def init_database(database_url: str):
    """Initialize the database engine and session maker."""
    global engine, async_session_maker
    
    engine = create_async_engine(
        database_url,
        echo=False,  # Set to True for SQL query logging
        pool_pre_ping=True,
        pool_recycle=300,
    )
    
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def close_database():
    """Close the database engine."""
    global engine
    if engine:
        await engine.dispose()
