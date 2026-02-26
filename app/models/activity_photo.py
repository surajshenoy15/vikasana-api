from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_session import ActivitySession
from app.models.activity_photo import ActivityPhoto
from app.models.events import Event  # adjust import if your Event model path differs


async def add_photo(
    db: AsyncSession,
    submission_id: int,     # this is ActivitySession.id
    student_id: int,
    seq_no: int,
    image_url: str,
    lat: float,
    lng: float,
    captured_at: datetime | None = None,
    sha256: str | None = None,
):
    # 1) Validate session belongs to student
    q = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == submission_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = q.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found for this student")

    # 2) Ensure session is in progress (if you have status)
    if hasattr(session, "status") and session.status not in ("in_progress", "IN_PROGRESS"):
        raise HTTPException(status_code=400, detail="Session already completed")

    # 3) Validate seq_no against event.required_photos (if session has event_id)
    if hasattr(session, "event_id") and session.event_id:
        rq = await db.execute(select(Event.required_photos).where(Event.id == session.event_id))
        required_photos = rq.scalar_one()
        if seq_no < 1 or seq_no > required_photos:
            raise HTTPException(status_code=400, detail=f"seq_no must be between 1 and {required_photos}")

    # 4) Upsert by (session_id, seq_no)
    pq = await db.execute(
        select(ActivityPhoto).where(
            ActivityPhoto.session_id == session.id,
            ActivityPhoto.seq_no == seq_no,
        )
    )
    existing = pq.scalar_one_or_none()

    if captured_at is None:
        captured_at = datetime.utcnow()

    if existing:
        existing.image_url = image_url
        existing.lat = float(lat)
        existing.lng = float(lng)
        existing.captured_at = captured_at
        if sha256 is not None:
            existing.sha256 = sha256

        await db.commit()
        await db.refresh(existing)
        return existing

    photo = ActivityPhoto(
        session_id=session.id,
        student_id=student_id,
        seq_no=seq_no,
        image_url=image_url,
        lat=float(lat),
        lng=float(lng),
        captured_at=captured_at,
        sha256=sha256,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo