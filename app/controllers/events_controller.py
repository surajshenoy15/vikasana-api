from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.events import Event, EventSubmission, EventSubmissionPhoto


# ---------------- ADMIN ----------------
async def create_event(db: AsyncSession, payload):
    event = Event(
        title=payload.title,
        description=payload.description,
        required_photos=payload.required_photos,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


# ---------------- STUDENT ----------------
async def list_active_events(db: AsyncSession):
    q = await db.execute(select(Event).where(Event.is_active == True))
    return q.scalars().all()


async def register_for_event(db: AsyncSession, student_id: int, event_id: int):
    # check event exists
    q = await db.execute(select(Event).where(Event.id == event_id))
    event = q.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    # prevent duplicate registration
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
    )

    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {"submission_id": submission.id, "status": submission.status}


# ---------------- PHOTO UPLOAD ----------------
async def add_photo(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    seq_no: int,
    image_url: str,
):
    # validate submission ownership
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

    # get event required photo count
    q = await db.execute(select(Event.required_photos).where(Event.id == submission.event_id))
    required_photos = q.scalar_one()

    if seq_no < 1 or seq_no > required_photos:
        raise HTTPException(
            status_code=400,
            detail=f"seq_no must be between 1 and {required_photos}"
        )

    # 🔁 RETAKE SUPPORT — check if photo already exists
    q = await db.execute(
        select(EventSubmissionPhoto).where(
            EventSubmissionPhoto.submission_id == submission_id,
            EventSubmissionPhoto.seq_no == seq_no
        )
    )
    existing_photo = q.scalar_one_or_none()

    if existing_photo:
        # Replace image (retake)
        existing_photo.image_url = image_url
        await db.commit()
        await db.refresh(existing_photo)
        return existing_photo

    # First time upload
    photo = EventSubmissionPhoto(
        submission_id=submission_id,
        seq_no=seq_no,
        image_url=image_url,
    )

    db.add(photo)
    await db.commit()
    await db.refresh(photo)

    return photo


# ---------------- FINAL SUBMIT ----------------
async def final_submit(
    db: AsyncSession,
    submission_id: int,
    student_id: int,
    description: str
):
    # validate submission ownership
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

    # get required photo count
    q = await db.execute(select(Event.required_photos).where(Event.id == submission.event_id))
    required_photos = q.scalar_one()

    # count uploaded photos
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

    # finalize submission
    submission.status = "submitted"
    submission.description = description
    submission.submitted_at = datetime.utcnow()

    await db.commit()
    await db.refresh(submission)

    return submission