# app/controllers/events_controller.py
from __future__ import annotations

from datetime import datetime
from datetime import date as date_type
from zoneinfo import ZoneInfo

from sqlalchemy import select, func, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.events import Event, EventSubmission, EventSubmissionPhoto
from app.core.event_thumbnail_storage import generate_event_thumbnail_presigned_put

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

# =========================================================
# Time helpers (IST)
# =========================================================

IST = ZoneInfo("Asia/Kolkata")


def _now_ist() -> datetime:
    return datetime.now(IST)


def _ensure_event_window(event: Event) -> None:
    """
    Enforces:
      - event must be active (is_active = True)
      - accessible ONLY on event_date
      - must be within start_time/end_time if configured
    """
    now = _now_ist()

    # ✅ block ended/inactive events
    if not getattr(event, "is_active", True):
        raise HTTPException(status_code=403, detail="Event has ended.")

    if not getattr(event, "event_date", None):
        raise HTTPException(status_code=400, detail="Event date not configured.")

    # must be the same day (IST date)
    if event.event_date != now.date():
        raise HTTPException(status_code=403, detail="Event is not available today.")

    # must be within time window if provided
    if getattr(event, "start_time", None) and now.time() < event.start_time:
        raise HTTPException(status_code=403, detail="Event has not started yet.")

    if getattr(event, "end_time", None) and now.time() > event.end_time:
        raise HTTPException(status_code=403, detail="Event has ended.")


async def get_event_thumbnail_upload_url(admin_id: int, filename: str, content_type: str):
    # (You may optionally validate content_type here using ALLOWED_IMAGE_TYPES)
    return await generate_event_thumbnail_presigned_put(
        filename=filename,
        content_type=content_type,
        admin_id=admin_id,
    )


# =========================================================
# ---------------------- ADMIN -----------------------------
# =========================================================

async def create_event(db: AsyncSession, payload):
    event = Event(
        title=payload.title,
        description=payload.description,
        required_photos=int(payload.required_photos or 3),
        is_active=True,

        event_date=getattr(payload, "event_date", None),
        start_time=getattr(payload, "start_time", None),
        end_time=getattr(payload, "end_time", None),

        thumbnail_url=getattr(payload, "thumbnail_url", None),
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def end_event(db: AsyncSession, event_id: int) -> Event:
    """
    Admin ends event now:
      - is_active = False
      - end_time = current IST datetime (TIMESTAMP column)
    """
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    if getattr(event, "is_active", True) is False:
        return event  # already ended

    event.is_active = False

    # IMPORTANT: end_time column is TIMESTAMP
    if hasattr(event, "end_time"):
        event.end_time = _now_ist()  # full datetime

    await db.commit()
    await db.refresh(event)
    return event

async def delete_event(db: AsyncSession, event_id: int) -> None:
    """
    Hard-delete an event and all its submissions + photos.
    """
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    sub_result = await db.execute(
        select(EventSubmission.id).where(EventSubmission.event_id == event_id)
    )
    submission_ids = [row[0] for row in sub_result.fetchall()]

    if submission_ids:
        await db.execute(
            sql_delete(EventSubmissionPhoto).where(
                EventSubmissionPhoto.submission_id.in_(submission_ids)
            )
        )
        await db.execute(
            sql_delete(EventSubmission).where(EventSubmission.event_id == event_id)
        )

    await db.execute(sql_delete(Event).where(Event.id == event_id))
    await db.commit()


async def list_event_submissions(db: AsyncSession, event_id: int):
    q = await db.execute(select(EventSubmission).where(EventSubmission.event_id == event_id))
    return q.scalars().all()


async def approve_submission(db: AsyncSession, submission_id: int):
    q = await db.execute(select(EventSubmission).where(EventSubmission.id == submission_id))
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be approved")

    submission.status = "approved"
    if hasattr(submission, "approved_at"):
        submission.approved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)
    return submission


async def reject_submission(db: AsyncSession, submission_id: int, reason: str):
    q = await db.execute(select(EventSubmission).where(EventSubmission.id == submission_id))
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be rejected")

    submission.status = "rejected"
    if hasattr(submission, "rejection_reason"):
        submission.rejection_reason = reason

    await db.commit()
    await db.refresh(submission)
    return submission


# =========================================================
# ---------------------- STUDENT ---------------------------
# =========================================================

async def list_active_events(db: AsyncSession):
    """
    Returns active events from today onwards (upcoming + today), using IST date.
    """
    today_ist = _now_ist().date()

    q = await db.execute(
        select(Event).where(
            Event.is_active == True,
            Event.event_date != None,
            Event.event_date >= today_ist
        ).order_by(
            Event.event_date.asc(),
            Event.start_time.asc().nulls_last(),
            Event.id.desc()
        )
    )
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    """
    Registration allowed only on event day + within window + active.
    """
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()

    if not event or not getattr(event, "is_active", True):
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event_id,
            EventSubmission.student_id == student_id,
        )
    )
    existing = q.scalar_one_or_none()
    if existing:
        return {"submission_id": existing.id, "status": existing.status}

    submission = EventSubmission(
        event_id=event_id,
        student_id=student_id,
        status="in_progress",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {"submission_id": submission.id, "status": submission.status}


# =========================================================
# ---------------------- PHOTO UPLOAD ----------------------
# =========================================================

async def add_photo(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
):
    """
    Adds/updates a photo for an EventSubmissionPhoto table.
    Use this only if you want event_submission_photos storage.
    """
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Submission already completed")

    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    required_photos = int(getattr(event, "required_photos", 3) or 3)
    if seq_no < 1 or seq_no > required_photos:
        raise HTTPException(status_code=400, detail=f"seq_no must be between 1 and {required_photos}")

    q = await db.execute(
        select(EventSubmissionPhoto).where(
            EventSubmissionPhoto.submission_id == submission_id,
            EventSubmissionPhoto.seq_no == seq_no
        )
    )
    existing_photo = q.scalar_one_or_none()

    if existing_photo:
        existing_photo.image_url = image_url
        await db.commit()
        await db.refresh(existing_photo)
        return existing_photo

    photo = EventSubmissionPhoto(
        submission_id=submission_id,
        seq_no=seq_no,
        image_url=image_url,
    )
    db.add(photo)
    await db.commit()
    await db.refresh(photo)
    return photo


# =========================================================
# ---------------------- FINAL SUBMIT ----------------------
# =========================================================

async def final_submit(db: AsyncSession, submission_id: int, student_id: int, description: str):
    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.id == submission_id,
            EventSubmission.student_id == student_id
        )
    )
    submission = q.scalar_one_or_none()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "in_progress":
        raise HTTPException(status_code=400, detail="Already submitted")

    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    _ensure_event_window(event)

    required_photos = int(getattr(event, "required_photos", 3) or 3)

    q = await db.execute(
        select(func.count(EventSubmissionPhoto.id)).where(
            EventSubmissionPhoto.submission_id == submission_id
        )
    )
    uploaded_photos = int(q.scalar() or 0)

    if uploaded_photos < required_photos:
        raise HTTPException(
            status_code=400,
            detail=(
                f"You must upload at least {required_photos} photos before submitting. "
                f"Currently uploaded: {uploaded_photos}"
            )
        )

    submission.status = "submitted"
    submission.description = description
    if hasattr(submission, "submitted_at"):
        submission.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)
    return submission