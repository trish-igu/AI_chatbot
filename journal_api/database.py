from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class JournalEntry(Base):
    __tablename__ = "journal_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    mood = Column(String(50), nullable=True)
    tags = Column(JSONB, nullable=True)
    attachments = Column(JSONB, nullable=True)
    is_private = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


class MoodLog(Base):
    __tablename__ = "mood_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), nullable=False)
    mood = Column(JSONB, nullable=False)  # {feeling, intensity}
    mood_score = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    activities = Column(JSONB, nullable=True)
    sleep = Column(JSONB, nullable=True)
    logged_at = Column(DateTime(timezone=True), nullable=False, default=func.now())


engine = None
async_session_maker = None


async def init_database(database_url: str):
    global engine, async_session_maker
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_recycle=300,
    )
    async_session_maker = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )


async def get_db() -> AsyncSession:
    if async_session_maker is None:
        raise RuntimeError("Database not initialized. Call init_database() first.")
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


