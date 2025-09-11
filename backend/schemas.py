"""
Pydantic models for API request/response validation.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    conversation_id: Optional[UUID] = Field(None, description="UUID of existing conversation, or None for new conversation")
    message: str = Field(..., min_length=1, max_length=4000, description="User's message to the AI")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    
    conversation_id: UUID = Field(..., description="UUID of the conversation")
    response: str = Field(..., description="AI's response to the user's message")


class ConversationSummary(BaseModel):
    """Model for conversation summary information."""
    
    conversation_id: UUID
    user_id: UUID
    title: Optional[str] = None
    conversation_summary: Optional[str] = None
    model: Optional[str] = None
    token_usage: Optional[Dict[str, Any]] = None
    status: str
    last_message_at: Optional[datetime] = None
    created_at: datetime
    archived: bool


class MessageHistory(BaseModel):
    """Model for individual message in conversation history."""
    
    id: UUID
    conversation_id: UUID
    user_id: UUID
    role: str
    content: Dict[str, Any]
    created_at: datetime


class ConversationWithHistory(BaseModel):
    """Model for conversation with its message history."""
    
    conversation: ConversationSummary
    messages: List[MessageHistory]


class ErrorResponse(BaseModel):
    """Model for error responses."""
    
    error: str = Field(..., description="Error message")
    detail: Optional[str] = Field(None, description="Additional error details")


class HealthResponse(BaseModel):
    """Model for health check response."""
    
    status: str = Field(..., description="Health status")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Response timestamp")