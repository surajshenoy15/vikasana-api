from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException

from app.models.activity_photo import ActivityPhoto
from app.models.activity_session import ActivitySession


async def add_activity_photo(
    db: AsyncSession,
    session_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
    lat: float,
    lng: float,
    captured_at: datetime | None = None,
):
    # Validate session belongs to student
    q = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found for this student")

    captured_at = captured_at or datetime.utcnow()

    # Upsert by (session_id, seq_no) - your UNIQUE index enforces this
    q = await db.execute(
        select(ActivityPhoto).where(
            ActivityPhoto.session_id == session_id,
            ActivityPhoto.seq_no == seq_no,
        )
    )
    existing = q.scalar_one_or_none()

    if existing:
        existing.image_url = image_url
        existing.lat = lat
        existing.lng = lng
        existing.captured_at = captured_at
        existing.student_id = student_id  # ensure always set
        await db.commit()
        await db.refresh(existing)
        return existing

    photo = ActivityPhoto(
        session_id=session_id,
        student_id=student_id,
        seq_no=seq_no,
        image_url=image_url,
        lat=lat,
        lng=lng,
        captured_at=captured_at,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo