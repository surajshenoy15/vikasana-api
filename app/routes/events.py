# app/routes/events.py  ✅ FULL UPDATED (clean + permanent fix)
from __future__ import annotations

from typing import List
from datetime import datetime, date as date_type, time as time_type, timezone

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin
from app.core.activity_storage import upload_activity_image

from app.models.activity_session import ActivitySession
from app.models.activity_photo import ActivityPhoto
from app.models.events import Event
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

from app.schemas.certificate import StudentCertificateOut

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
    list_student_event_certificates,
    regenerate_event_certificates,
    auto_approve_event_from_sessions,
)

router = APIRouter(tags=["Events"])


# =========================================================
# ---------------------- HELPERS --------------------------
# =========================================================

def _combine_event_datetime_ist_naive(event_date: date_type, t: time_type) -> datetime:
    # DB stores TIMESTAMP WITHOUT TZ for end_time
    return datetime.combine(event_date, t).replace(tzinfo=None)


def _as_naive_datetime_for_end_time(event_date: date_type | None, end_val):
    """
    Accepts:
      - None
      - time -> converts to naive datetime using event_date
      - datetime -> strips tzinfo to naive
    """
    if end_val is None:
        return None

    if isinstance(end_val, datetime):
        return end_val.replace(tzinfo=None)

    if isinstance(end_val, time_type):
        if not event_date:
            raise HTTPException(
                status_code=422,
                detail="event_date is required when end_time is a time value",
            )
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


def _normalize_activity_type_ids(payload: EventCreateIn) -> list[int]:
    """
    ✅ Permanent fix:
    Normalize whatever frontend sends into a clean list[int]
    AND enforce at least 1 id.
    """
    raw = getattr(payload, "activity_type_ids", None) or []

    # sometimes frontend sends objects [{id:1},{id:2}]
    if isinstance(raw, list) and raw and isinstance(raw[0], dict):
        raw = [x.get("id") for x in raw]

    # sometimes frontend sends csv string "1,2"
    if isinstance(raw, str):
        raw = [x.strip() for x in raw.split(",") if x.strip()]

    ids: list[int] = []
    if isinstance(raw, list):
        for x in raw:
            try:
                v = int(x)
                if v > 0:
                    ids.append(v)
            except Exception:
                pass

    ids = sorted(set(ids))
    return ids


# =========================================================
# ---------------------- ADMIN -----------------------------
# =========================================================

@router.post("/admin/events", response_model=EventOut)
async def admin_create_event_api(
    payload: EventCreateIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    # create_event() already blocks if no activity types (permanent fix)
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

    # ✅ Permanent fix: force activity types while updating too
    ids = _normalize_activity_type_ids(payload)
    if not ids:
        raise HTTPException(status_code=422, detail="Please select at least 1 activity type for this event.")

    ev.title = (payload.title or "").strip()
    ev.description = (payload.description or "").strip() or None
    ev.required_photos = int(payload.required_photos or 3)

    ev.event_date = payload.event_date
    ev.start_time = payload.start_time
    ev.end_time = _as_naive_datetime_for_end_time(payload.event_date, payload.end_time)

    ev.thumbnail_url = payload.thumbnail_url
    ev.venue_name = (payload.venue_name or "").strip() or None
    ev.maps_url = (payload.maps_url or "").strip() or None

    # ✅ replace mapping atomically
    await db.execute(sql_delete(EventActivityType).where(EventActivityType.event_id == event_id))
    for at_id in ids:
        db.add(EventActivityType(event_id=event_id, activity_type_id=at_id))

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


# ✅ One-click: auto approve (face verified) + issue certificates
@router.post("/admin/events/{event_id}/approve-and-issue")
async def admin_auto_approve_and_issue(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await auto_approve_event_from_sessions(db, event_id)


# ✅ Regenerate certificates (idempotent)
@router.post("/admin/events/{event_id}/certificates/regenerate")
async def admin_regenerate_event_certificates(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await regenerate_event_certificates(db, event_id)


@router.get("/admin/events", response_model=list[EventOut])
async def admin_list_events_api(
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    res = await db.execute(select(Event).order_by(Event.id.desc()))
    events = res.scalars().all()
    return [_event_out_dict(ev) for ev in events]


# =========================================================
# ---------------------- STUDENT ---------------------------
# =========================================================

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


@router.get("/student/events/{event_id}/certificates", response_model=list[StudentCertificateOut])
async def student_event_certificates(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await list_student_event_certificates(db=db, student_id=student.id, event_id=event_id)


@router.post("/student/events/{event_id}/register", response_model=RegisterOut)
async def register_event(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await register_for_event(db, student.id, event_id)


# NOTE: This endpoint is currently using ActivitySession/ActivityPhoto model.
# If this is actually EVENT submission photos, you should switch to EventSubmissionPhoto logic.
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

        now_utc = datetime.now(timezone.utc)
        if existing:
            existing.image_url = image_url
            existing.student_id = student.id
            existing.lat = float(lats[idx])
            existing.lng = float(lngs[idx])
            existing.captured_at = now_utc
            photo = existing
        else:
            photo = ActivityPhoto(
                session_id=session.id,
                student_id=student.id,
                seq_no=seq_no,
                image_url=image_url,
                lat=float(lats[idx]),
                lng=float(lngs[idx]),
                captured_at=now_utc,
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


# =========================================================
# ---------------------- ADMIN REVIEW ----------------------
# =========================================================

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