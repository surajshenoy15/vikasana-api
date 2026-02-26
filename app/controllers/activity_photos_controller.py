# app/controllers/activity_photos_controller.py

from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select, and_
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

    # 2) Ensure session is in progress / draft (adjust allowed statuses)
    # Your sessions use: DRAFT, SUBMITTED, APPROVED, FLAGGED, REJECTED, EXPIRED
    if hasattr(session, "status"):
        status = (session.status or "").upper()
        if status != "DRAFT":
            raise HTTPException(status_code=400, detail=f"Cannot upload photos when session status is {status}")

    # 3) Validate seq_no against event.required_photos (if session has event_id)
    if getattr(session, "event_id", None):
        rq = await db.execute(select(Event.required_photos).where(Event.id == session.event_id))
        required_photos = rq.scalar_one_or_none()
        if required_photos is None:
            raise HTTPException(status_code=400, detail="Invalid event linked to session")

        required_photos = int(required_photos)
        if seq_no < 1 or seq_no > required_photos:
            raise HTTPException(status_code=400, detail=f"seq_no must be between 1 and {required_photos}")

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

    # 5) Compute duplicate (do NOT store in DB unless you add a column)
    is_duplicate = False
    if sha256:
        # duplicate within same session (recommended)
        q = select(ActivityPhoto.id).where(
            and_(
                ActivityPhoto.session_id == session_id,
                ActivityPhoto.sha256 == sha256,
            )
        )
        # if updating, ignore self
        if existing is not None:
            q = q.where(ActivityPhoto.id != existing.id)

        dup = await db.execute(q)
        is_duplicate = dup.scalar_one_or_none() is not None

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

            # return dict including is_duplicate
            return {
                "id": existing.id,
                "image_url": existing.image_url,
                "sha256": getattr(existing, "sha256", None),
                "captured_at": existing.captured_at,
                "lat": existing.lat,
                "lng": existing.lng,
                "is_duplicate": bool(is_duplicate),
            }

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

        return {
            "id": photo.id,
            "image_url": photo.image_url,
            "sha256": getattr(photo, "sha256", None),
            "captured_at": photo.captured_at,
            "lat": photo.lat,
            "lng": photo.lng,
            "is_duplicate": bool(is_duplicate),
        }

    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Photo for this seq_no already exists")