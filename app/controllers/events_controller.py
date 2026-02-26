# app/controllers/events_controller.py  ✅ FULL UPDATED
# - Fix: block tomorrow/future events from being REGISTERED/STARTED today
# - Fix: enforce event window (IST) for register, add_photo, final_submit
# - Keeps: list_active_events returns upcoming (>= today)
# - NOTE: This controller assumes EventSubmission represents the student's "submission/session" for an event.

from __future__ import annotations

from datetime import datetime, date
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
    Enforces: event can be accessed ONLY on the event day,
    and (optionally) within start_time/end_time if configured.
    """
    now = _now_ist()

    if not event.event_date:
        raise HTTPException(status_code=400, detail="Event date not configured.")

    # must be the same day
    if event.event_date != now.date():
        raise HTTPException(status_code=403, detail="Event is not available today.")

    # must be within time window if provided
    if event.start_time and now.time() < event.start_time:
        raise HTTPException(status_code=403, detail="Event has not started yet.")

    if event.end_time and now.time() > event.end_time:
        raise HTTPException(status_code=403, detail="Event has ended.")


async def get_event_thumbnail_upload_url(admin_id: int, filename: str, content_type: str):
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
        required_photos=payload.required_photos,
        is_active=True,

        # ✅ schedule
        event_date=getattr(payload, "event_date", None),
        start_time=getattr(payload, "start_time", None),
        end_time=getattr(payload, "end_time", None),

        thumbnail_url=getattr(payload, "thumbnail_url", None),
    )
    db.add(event)
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
    q = await db.execute(
        select(EventSubmission).where(EventSubmission.event_id == event_id)
    )
    return q.scalars().all()


async def approve_submission(db: AsyncSession, submission_id: int):
    q = await db.execute(
        select(EventSubmission).where(EventSubmission.id == submission_id)
    )
    submission = q.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be approved")

    submission.status = "approved"
    submission.approved_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)

    return submission


async def reject_submission(db: AsyncSession, submission_id: int, reason: str):
    q = await db.execute(
        select(EventSubmission).where(EventSubmission.id == submission_id)
    )
    submission = q.scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "submitted":
        raise HTTPException(status_code=400, detail="Only submitted items can be rejected")

    submission.status = "rejected"
    submission.rejection_reason = reason

    await db.commit()
    await db.refresh(submission)

    return submission


# =========================================================
# ---------------------- STUDENT ---------------------------
# =========================================================

async def list_active_events(db: AsyncSession):
    """
    Returns active events from today onwards (upcoming + today).
    UI can show Upcoming/Ongoing/Past by comparing dates.
    """
    today = date.today()
    q = await db.execute(
        select(Event).where(
            Event.is_active == True,
            Event.event_date != None,
            Event.event_date >= today
        ).order_by(
            Event.event_date.asc(),
            Event.start_time.asc().nulls_last(),
            Event.id.desc()
        )
    )
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    """
    IMPORTANT CHANGE:
    - Registration is allowed ONLY when the event is available today (and within start/end time if set).
    This prevents tomorrow's event from being started today.
    """
    q = await db.execute(select(Event).where(Event.id == event_id, Event.is_active == True))
    event = q.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # ✅ BLOCK future events (tomorrow etc.)
    _ensure_event_window(event)

    q = await db.execute(
        select(EventSubmission).where(
            EventSubmission.event_id == event_id,
            EventSubmission.student_id == student_id
        )
    )
    existing = q.scalar_one_or_none()

    if existing:
        return {"submission_id": existing.id, "status": existing.status}

    submission = EventSubmission(
        event_id=event_id,
        student_id=student_id,
        status="in_progress"
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
    Adds/updates a photo for an EventSubmission.
    ✅ Now enforces event window (prevents uploading before event day/time)
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

    # ✅ fetch event and block if not within allowed window
    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    _ensure_event_window(event)

    q = await db.execute(select(Event.required_photos).where(Event.id == submission.event_id))
    required_photos = q.scalar_one()

    if seq_no < 1 or seq_no > required_photos:
        raise HTTPException(
            status_code=400,
            detail=f"seq_no must be between 1 and {required_photos}"
        )

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

async def final_submit(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    description: str
):
    """
    ✅ Now enforces event window (prevents submitting before event day/time)
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
        raise HTTPException(status_code=400, detail="Already submitted")

    # ✅ fetch event and block if not within allowed window
    evq = await db.execute(select(Event).where(Event.id == submission.event_id))
    event = evq.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    _ensure_event_window(event)

    q = await db.execute(select(Event.required_photos).where(Event.id == submission.event_id))
    required_photos = q.scalar_one()

    q = await db.execute(
        select(func.count(EventSubmissionPhoto.id)).where(
            EventSubmissionPhoto.submission_id == submission_id
        )
    )
    uploaded_photos = q.scalar() or 0

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
    submission.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)

    return submission