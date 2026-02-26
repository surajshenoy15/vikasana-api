# app/controllers/activity_photos_controller.py

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_photo import ActivityPhoto
from app.models.activity_session import ActivitySession
from app.models.events import Event


async def add_activity_photo(
    db: AsyncSession,
    session_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
    lat: float,
    lng: float,
    captured_at: datetime | None = None,
    sha256: str | None = None,
):
    # 1) Validate session belongs to student
    res = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found for this student")

    # 2) Ensure session is in progress (optional status)
    if hasattr(session, "status"):
        status = (session.status or "").lower()
        if status not in ("in_progress", "in progress", "in-progress"):
            raise HTTPException(status_code=400, detail="Session already completed")

    # 3) Validate seq_no against event.required_photos (if session has event_id)
    if getattr(session, "event_id", None):
        rq = await db.execute(
            select(Event.required_photos).where(Event.id == session.event_id)
        )
        required_photos = rq.scalar_one_or_none()
        if required_photos is None:
            raise HTTPException(status_code=400, detail="Invalid event linked to session")

        required_photos = int(required_photos)
        if seq_no < 1 or seq_no > required_photos:
            raise HTTPException(
                status_code=400,
                detail=f"seq_no must be between 1 and {required_photos}",
            )

    # 4) Upsert by (session_id, seq_no)
    res = await db.execute(
        select(ActivityPhoto).where(
            ActivityPhoto.session_id == session_id,
            ActivityPhoto.seq_no == seq_no,
        )
    )
    existing = res.scalar_one_or_none()

    if captured_at is None:
        captured_at = datetime.now(timezone.utc)

    try:
        if existing:
            existing.image_url = image_url
            existing.lat = float(lat)
            existing.lng = float(lng)
            existing.captured_at = captured_at
            existing.student_id = student_id
            if sha256 is not None and hasattr(existing, "sha256"):
                existing.sha256 = sha256

            await db.commit()
            await db.refresh(existing)
            return existing

        photo = ActivityPhoto(
            session_id=session_id,
            student_id=student_id,
            seq_no=seq_no,
            image_url=image_url,
            lat=float(lat),
            lng=float(lng),
            captured_at=captured_at,
            **({"sha256": sha256} if sha256 is not None else {}),
        )
        db.add(photo)
        await db.commit()
        await db.refresh(photo)
        return photo

    except IntegrityError:
        await db.rollback()
        # Happens if two requests insert same (session_id, seq_no) concurrently
        raise HTTPException(status_code=409, detail="Photo for this seq_no already exists")