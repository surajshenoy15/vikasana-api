# app/routes/events.py  ✅ UPDATED — adds PUT /admin/events/{event_id}
from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin
from app.core.activity_storage import upload_activity_image

from app.models.activity_session import ActivitySession
from app.models.activity_photo import ActivityPhoto
from app.models.events import Event

from app.schemas.events import (
    EventCreateIn,
    EventOut,
    RegisterOut,
    PhotoOut,
    PhotosUploadOut,
    FinalSubmitIn,
    SubmissionOut,
    AdminSubmissionOut,
    RejectIn,
    ThumbnailUploadUrlIn,
    ThumbnailUploadUrlOut,
)

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
)

router = APIRouter(tags=["Events"])


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


# ⚠️ Keep thumbnail-upload-url BEFORE /{event_id} so FastAPI doesn't
# treat "thumbnail-upload-url" as an integer path param.
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


# ✅ NEW: Full event edit
@router.put("/admin/events/{event_id}", response_model=EventOut)
async def admin_update_event_api(
    event_id: int,
    payload: EventCreateIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """
    Update any field of an existing event.
    Uses the same EventCreateIn schema as creation so all fields are editable:
    title, description, event_date, event_time, venue_name, venue_maps_url,
    required_photos, activity_list, thumbnail_url.
    """
    res = await db.execute(select(Event).where(Event.id == event_id))
    ev = res.scalar_one_or_none()
    if not ev:
        raise HTTPException(status_code=404, detail="Event not found")

    # Apply all fields from payload
    ev.title = payload.title.strip()
    ev.description = (payload.description or "").strip() or None

    # Support both field name variants the schema might use
    ev.event_date = getattr(payload, "event_date", None) or getattr(payload, "date", None)
    ev.event_time = getattr(payload, "event_time", None) or getattr(payload, "time", None)

    ev.venue_name = (payload.venue_name or "").strip() or None
    ev.venue_maps_url = (payload.venue_maps_url or "").strip() or None
    ev.required_photos = int(payload.required_photos or 3)
    ev.activity_list = payload.activity_list or []
    ev.thumbnail_url = payload.thumbnail_url or None

    await db.commit()
    await db.refresh(ev)
    return ev


@router.delete("/admin/events/{event_id}", status_code=204)
async def admin_delete_event_api(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    await delete_event(db, event_id)


# ══════════════════════════════════════════════
# STUDENT — Events
# ══════════════════════════════════════════════

@router.get("/student/events", response_model=list[EventOut])
async def student_events(
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await list_active_events(db)


@router.post("/student/events/{event_id}/register", response_model=RegisterOut)
async def register_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await register_for_event(db, student.id, event_id)


# ✅ Multi-image upload (writes to activity_photos)
@router.post(
    "/student/submissions/{submission_id}/photos",
    response_model=PhotosUploadOut,
)
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