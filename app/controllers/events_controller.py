from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from sqlalchemy import select, delete as sql_delete

from app.models.events import Event, EventSubmission, EventSubmissionPhoto

from app.core.event_thumbnail_storage import generate_event_thumbnail_presigned_put

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


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

        # ✅ SAVE THESE
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
    # 1. Check event exists
    result = await db.execute(select(Event).where(Event.id == event_id))
    event = result.scalar_one_or_none()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2. Get all submission IDs for this event
    sub_result = await db.execute(
        select(EventSubmission.id).where(EventSubmission.event_id == event_id)
    )
    submission_ids = [row[0] for row in sub_result.fetchall()]

    if submission_ids:
        # 2a. Delete all photos for those submissions
        await db.execute(
            sql_delete(EventSubmissionPhoto).where(
                EventSubmissionPhoto.submission_id.in_(submission_ids)
            )
        )
        # 2b. Delete all submissions for this event
        await db.execute(
            sql_delete(EventSubmission).where(
                EventSubmission.event_id == event_id
            )
        )

    # 3. Delete the event itself
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
    q = await db.execute(select(Event).where(Event.is_active == True))
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()

    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

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
            detail=f"You must upload at least {required_photos} photos before submitting. "
                   f"Currently uploaded: {uploaded_photos}"
        )

    submission.status = "submitted"
    submission.description = description
    submission.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)

    return submission