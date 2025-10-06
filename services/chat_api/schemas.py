"""
Pydantic models for API request/response validation.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, EmailStr, validator
from uuid import UUID
from datetime import datetime
import re


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


# Authentication Schemas
class UserRegister(BaseModel):
    """User registration request model."""
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password (8-100 characters)")
    first_name: Optional[str] = Field(None, max_length=100, description="First name")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name")
    display_name: Optional[str] = Field(None, max_length=150, description="Display name")
    phone_number: Optional[str] = Field(None, max_length=20, description="Phone number")
    is_caregiver: bool = Field(default=False, description="Is this user a caregiver?")
    
    @validator('password')
    def validate_password(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one number')
        if not re.search(r'[!@#$%^&*(),.?":{}|<>]', v):
            raise ValueError('Password must contain at least one special character')
        return v
    
    @validator('phone_number')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[\d\s\-\(\)]+$', v):
            raise ValueError('Invalid phone number format')
        return v


class UserLogin(BaseModel):
    """User login request model."""
    email: EmailStr = Field(..., description="User's email address")
    password: str = Field(..., min_length=1, description="User's password")


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user_id: UUID = Field(..., description="User ID")
    display_name: Optional[str] = Field(None, description="User's display name")


class UserProfile(BaseModel):
    """User profile response model."""
    id: UUID = Field(..., description="User ID")
    email: Optional[str] = Field(None, description="User's email")
    first_name: Optional[str] = Field(None, description="First name")
    last_name: Optional[str] = Field(None, description="Last name")
    display_name: Optional[str] = Field(None, description="Display name")
    avatar: Optional[str] = Field(None, description="Avatar URL")
    phone_number: Optional[str] = Field(None, description="Phone number")
    phone_verified: bool = Field(..., description="Phone verification status")
    is_caregiver: bool = Field(..., description="Caregiver status")
    care_receivers_count: int = Field(..., description="Number of care receivers")
    onboarding_completed: bool = Field(..., description="Onboarding completion status")
    onboarding_current_step: int = Field(..., description="Current onboarding step")
    created_at: datetime = Field(..., description="Account creation date")
    last_login_at: Optional[datetime] = Field(None, description="Last login date")
    updated_at: Optional[datetime] = Field(None, description="Last update date")


class UserUpdate(BaseModel):
    """User profile update request model."""
    first_name: Optional[str] = Field(None, max_length=100, description="First name")
    last_name: Optional[str] = Field(None, max_length=100, description="Last name")
    display_name: Optional[str] = Field(None, max_length=150, description="Display name")
    avatar: Optional[str] = Field(None, max_length=500, description="Avatar URL")
    phone_number: Optional[str] = Field(None, max_length=20, description="Phone number")
    is_caregiver: Optional[bool] = Field(None, description="Caregiver status")
    preferences: Optional[Dict[str, Any]] = Field(None, description="User preferences")
    
    @validator('phone_number')
    def validate_phone(cls, v):
        if v and not re.match(r'^\+?[\d\s\-\(\)]+$', v):
            raise ValueError('Invalid phone number format')
        return v


# Greeting Schemas
class GreetingResponse(BaseModel):
    """Response model for assistant-initiated greeting."""
    conversation_id: UUID = Field(..., description="UUID of the new conversation started by the assistant")
    greeting: str = Field(..., description="Assistant's greeting message")


