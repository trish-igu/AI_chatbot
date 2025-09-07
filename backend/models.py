"""
SQLAlchemy ORM models for the database tables, corrected to match the final schema.
"""

import uuid
from sqlalchemy import (
    Column, 
    UUID as UUID_TYPE, 
    String, 
    DateTime, 
    func, 
    JSON, 
    ForeignKey, 
    Text, 
    Boolean
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    """
    Represents a user in the system. The primary key is 'id'.
    """
    __tablename__ = 'users'
    id = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, nullable=False)
    

class Conversation(Base):
    """
    Represents a single conversation session, matching the 'chatbot_conversation_audit' table.
    """
    __tablename__ = 'chatbot_conversation_audit'
    conversation_id = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID_TYPE(as_uuid=True), ForeignKey('users.id'), nullable=False)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    last_message_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    conversation_summary = Column(Text)
    model = Column(String(100))
    token_usage = Column(JSON)
    status = Column(String(50))
    archived = Column(Boolean, default=False)

    user = relationship("User")

class ChatbotUserMemory(Base):
    """
    Represents a single message within a conversation.
    """
    __tablename__ = 'chatbot_user_memory'
    id = Column(UUID_TYPE(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID_TYPE(as_uuid=True), ForeignKey('chatbot_conversation_audit.conversation_id'), nullable=False)
    user_id = Column(UUID_TYPE(as_uuid=True), ForeignKey('users.id'), nullable=False)
    role = Column(String(50), nullable=False)  # 'user' or 'assistant'
    content = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    user = relationship("User")
    conversation = relationship("Conversation")