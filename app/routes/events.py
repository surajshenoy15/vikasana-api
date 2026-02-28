# app/routes/events.py
from typing import List
from datetime import datetime, date as date_type, time as time_type
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin
from app.core.activity_storage import upload_activity_image

from app.models.activity_session import ActivitySession
from app.models.activity_photo import ActivityPhoto
from app.models.events import Event

# ✅ event ↔ activity_type mapping
from app.models.event_activity_type import EventActivityType

from app.schemas.events import (
    EventCreateIn,
    EventOut,
    RegisterOut,
    PhotosUploadOut,
    FinalSubmitIn,
    SubmissionOut,
    AdminSubmissionOut,
    RejectIn,
    ThumbnailUploadUrlIn,
    ThumbnailUploadUrlOut,
)

# ✅ certificates schema
from app.schemas.certificates import StudentCertificateOut

from app.controllers.events_controller import (
    create_event,
    delete_event,
    list_active_events,
    register_for_event,
    final_submit,
    list_event_submissions,
    approve_submission,
    reject_submission,
    get_event_thumbnail_upload_url,
    end_event,
    list_student_event_certificates,   # ✅ NEW
)

router = APIRouter(tags=["Events"])
IST = ZoneInfo("Asia/Kolkata")


def _combine_event_datetime_ist_naive(event_date: date_type, t: time_type) -> datetime:
    return datetime.combine(event_date, t).replace(tzinfo=None)


def _as_naive_datetime_for_end_time(event_date: date_type | None, end_val):
    if end_val is None:
        return None

    if isinstance(end_val, datetime):
        return end_val.replace(tzinfo=None)

    if isinstance(end_val, time_type):
        if not event_date:
            raise HTTPException(status_code=422, detail="event_date is required when end_time is a time value")
        return _combine_event_datetime_ist_naive(event_date, end_val)

    raise HTTPException(status_code=422, detail="Invalid end_time type")


def _event_out_dict(ev: Event) -> dict:
    end_val = getattr(ev, "end_time", None)
    end_time = end_val.time() if isinstance(end_val, datetime) else end_val

    return {
        "id": ev.id,
        "title": ev.title,
        "description": ev.description,
        "required_photos": ev.required_photos,
        "is_active": bool(getattr(ev, "is_active", True)),
        "event_date": ev.event_date,
        "start_time": ev.start_time,
        "end_time": end_time,
        "thumbnail_url": ev.thumbnail_url,
        "venue_name": getattr(ev, "venue_name", None),
        "maps_url": getattr(ev, "maps_url", None),
    }


# ══════════════════════════════════════════════
# ADMIN — Events CRUD
# ══════════════════════════════════════════════

@router.post("/admin/events", response_model=EventOut)
async def admin_create_event_api(
    payload: EventCreateIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await create_event(db, payload)


@router.post("/admin/events/thumbnail-upload-url", response_model=ThumbnailUploadUrlOut)
async def admin_event_thumbnail_upload_url(
    payload: ThumbnailUploadUrlIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await get_event_thumbnail_upload_url(
        admin_id=admin.id,
        filename=payload.filename,
        content_type=payload.content_type,
    )


@router.put("/admin/events/{event_id}", response_model=EventOut)
async def admin_update_event_api(
    event_id: int,
    payload: EventCreateIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    res = await db.execute(select(Event).where(Event.id == event_id))
    ev = res.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    ev.title = payload.title.strip()
    ev.description = (payload.description or "").strip() or None
    ev.required_photos = int(payload.required_photos or 3)

    ev.event_date = payload.event_date
    ev.start_time = payload.start_time
    ev.end_time = _as_naive_datetime_for_end_time(payload.event_date, payload.end_time)

    ev.thumbnail_url = payload.thumbnail_url
    ev.venue_name = (payload.venue_name or "").strip() or None
    ev.maps_url = (payload.maps_url or "").strip() or None

    # ✅ replace event activity types mapping
    await db.execute(sql_delete(EventActivityType).where(EventActivityType.event_id == event_id))
    for at_id in getattr(payload, "activity_type_ids", []) or []:
        db.add(EventActivityType(event_id=event_id, activity_type_id=int(at_id)))

    await db.commit()
    await db.refresh(ev)
    return _event_out_dict(ev)


@router.delete("/admin/events/{event_id}", status_code=204)
async def admin_delete_event_api(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    await delete_event(db, event_id)


@router.post("/admin/events/{event_id}/end", response_model=EventOut)
async def admin_end_event_api(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await end_event(db, event_id)


# ══════════════════════════════════════════════
# STUDENT — Events
# ══════════════════════════════════════════════

@router.get("/student/events", response_model=list[EventOut])
async def student_events(
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await list_active_events(db)


@router.get("/student/events/{event_id}", response_model=EventOut)
async def student_event_detail(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    res = await db.execute(select(Event).where(Event.id == event_id))
    ev = res.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")
    return _event_out_dict(ev)


# ✅ Certificates list for this student + this event
@router.get("/student/events/{event_id}/certificates", response_model=list[StudentCertificateOut])
async def student_event_certificates(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # ✅ IMPORTANT: returns [] if none, not 404
    return await list_student_event_certificates(db=db, student_id=student.id, event_id=event_id)


@router.post("/student/events/{event_id}/register", response_model=RegisterOut)
async def register_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await register_for_event(db, student.id, event_id)


@router.post("/student/submissions/{submission_id}/photos", response_model=PhotosUploadOut)
async def upload_photos(
    submission_id: int,
    start_seq: int = Query(..., description="Starting sequence number, e.g., 1"),
    images: List[UploadFile] = File(..., description="Upload multiple files with key 'images'"),
    lats: List[float] = Form(..., description="Latitude per image (same order as images)"),
    lngs: List[float] = Form(..., description="Longitude per image (same order as images)"),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    session_res = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == submission_id,
            ActivitySession.student_id == student.id,
        )
    )
    session = session_res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Submission/Session not found for this student")

    if len(lats) != len(images) or len(lngs) != len(images):
        raise HTTPException(status_code=422, detail="lats/lngs count must match number of images")

    results: List[ActivityPhoto] = []
    seq_no = start_seq

    for idx, img in enumerate(images):
        file_bytes = await img.read()
        if not file_bytes:
            continue

        image_url = await upload_activity_image(
            file_bytes=file_bytes,
            content_type=img.content_type or "application/octet-stream",
            filename=img.filename or f"photo_{seq_no}.jpg",
            student_id=student.id,
            session_id=session.id,
        )

        photo_res = await db.execute(
            select(ActivityPhoto).where(
                ActivityPhoto.session_id == session.id,
                ActivityPhoto.seq_no == seq_no,
            )
        )
        existing = photo_res.scalar_one_or_none()

        if existing:
            existing.image_url = image_url
            existing.student_id = student.id
            existing.lat = float(lats[idx])
            existing.lng = float(lngs[idx])
            existing.captured_at = datetime.utcnow()
            photo = existing
        else:
            photo = ActivityPhoto(
                session_id=session.id,
                student_id=student.id,
                seq_no=seq_no,
                image_url=image_url,
                lat=float(lats[idx]),
                lng=float(lngs[idx]),
                captured_at=datetime.utcnow(),
            )
            db.add(photo)

        await db.commit()
        await db.refresh(photo)
        results.append(photo)
        seq_no += 1

    return PhotosUploadOut(session_id=session.id, photos=results)


@router.post("/student/submissions/{submission_id}/submit", response_model=SubmissionOut)
async def submit_event(
    submission_id: int,
    payload: FinalSubmitIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await final_submit(db, submission_id, student.id, payload.description)


# ══════════════════════════════════════════════
# ADMIN — Review submissions
# ══════════════════════════════════════════════

@router.get("/admin/events/{event_id}/submissions", response_model=list[AdminSubmissionOut])
async def admin_list_event_submissions(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await list_event_submissions(db, event_id)


@router.post("/admin/submissions/{submission_id}/approve", response_model=AdminSubmissionOut)
async def approve_event_submission_api(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await approve_submission(db, submission_id)


@router.post("/admin/submissions/{submission_id}/reject", response_model=AdminSubmissionOut)
async def reject_event_submission_api(
    submission_id: int,
    payload: RejectIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await reject_submission(db, submission_id, payload.reason)