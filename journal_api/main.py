import uuid
from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database import init_database, get_db, JournalEntry, MoodLog
from schemas import (
    CreateJournalEntryRequest, JournalEntryResponse,
    CreateMoodLogRequest, MoodLogResponse,
)
from auth import get_current_user_id
from storage import upload_attachments

from sqlalchemy import select, desc


app = FastAPI(title="Journal & Mood Service", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    await init_database(settings.database_url)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/api/journal/entries", response_model=dict)
async def create_journal_entry(
    body: CreateJournalEntryRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    # Upload attachments if configured
    normalized_attachments = upload_attachments(body.attachments, str(user_id)) if body.attachments else None

    entry = JournalEntry(
        user_id=user_id,
        title=body.title,
        content=body.content,
        mood=body.mood,
        tags=body.tags,
        attachments=normalized_attachments,
        is_private=body.is_private,
    )
    db.add(entry)
    await db.flush()
    await db.commit()
    return {
        "status": "success",
        "message": "Journal entry created successfully.",
        "entryId": str(entry.id),
    }


@app.get("/api/journal/entries", response_model=List[JournalEntryResponse])
async def list_journal_entries(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    before_id: Optional[uuid.UUID] = Query(None, description="Keyset pagination: return items before this id"),
):
    # Keyset pagination: order by created_at desc, id tie-breaker
    stmt = select(JournalEntry).where(JournalEntry.user_id == user_id).order_by(desc(JournalEntry.created_at))
    # Simple keyset using created_at or id can be added later; for now, limit only
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    return [
        JournalEntryResponse(
            id=row.id,
            user_id=row.user_id,
            title=row.title,
            content=row.content,
            mood=row.mood,
            tags=row.tags,
            attachments=row.attachments,
            is_private=row.is_private,
            created_at=row.created_at,
        )
        for row in rows
    ]


@app.post("/api/mood/logs", response_model=dict)
async def log_mood(
    body: CreateMoodLogRequest,
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
):
    log = MoodLog(
        user_id=user_id,
        mood=body.mood.dict(),
        mood_score=body.mood_score,
        notes=body.notes,
        activities=body.activities,
        sleep=body.sleep,
    )
    db.add(log)
    await db.flush()
    await db.commit()
    return {
        "status": "success",
        "message": "Mood logged successfully.",
        "logId": str(log.id),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)


