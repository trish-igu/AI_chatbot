from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class CreateJournalEntryRequest(BaseModel):
    title: str
    content: str
    mood: Optional[str] = None
    tags: Optional[List[str]] = None
    attachments: Optional[Dict[str, Any]] = None
    is_private: bool = True


class JournalEntryResponse(BaseModel):
    id: UUID
    user_id: UUID
    title: str
    content: str
    mood: Optional[str] = None
    tags: Optional[List[str]] = None
    attachments: Optional[Dict[str, Any]] = None
    is_private: bool
    created_at: datetime


class Mood(BaseModel):
    feeling: str
    intensity: Optional[str] = None


class CreateMoodLogRequest(BaseModel):
    mood: Mood
    mood_score: Optional[int] = None
    notes: Optional[str] = None
    activities: Optional[List[str]] = None
    sleep: Optional[Dict[str, Any]] = None


class MoodLogResponse(BaseModel):
    id: UUID
    user_id: UUID
    mood: Dict[str, Any]
    mood_score: Optional[int]
    notes: Optional[str]
    activities: Optional[List[str]]
    sleep: Optional[Dict[str, Any]]
    logged_at: datetime


