from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin
from app.core.activity_storage import upload_activity_image

from app.models.activity_session import ActivitySession

from app.schemas.events import (
    EventCreateIn,
    EventOut,
    RegisterOut,
    PhotoOut,
    FinalSubmitIn,
    SubmissionOut,
    AdminSubmissionOut,
    RejectIn,
    ThumbnailUploadUrlIn,
    ThumbnailUploadUrlOut,
    PhotosUploadOut,  # ✅ REQUIRED (fixes NameError)
)

from app.controllers.events_controller import (
    create_event,
    delete_event,
    list_active_events,
    register_for_event,
    add_photo,
    final_submit,
    list_event_submissions,
    approve_submission,
    reject_submission,
    get_event_thumbnail_upload_url,
)

router = APIRouter(tags=["Events"])


# ---------------- ADMIN ----------------

@router.post("/admin/events", response_model=EventOut)
async def admin_create_event_api(
    payload: EventCreateIn,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await create_event(db, payload)


# ⚠️ IMPORTANT: keep this BEFORE /admin/events/{event_id}
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


@router.delete("/admin/events/{event_id}", status_code=204)
async def admin_delete_event_api(
    event_id: int,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    """Delete an event and all its submissions + photos. Returns 204."""
    await delete_event(db, event_id)


# ---------------- STUDENT ----------------

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


# ✅ MULTI UPLOAD
@router.post(
    "/student/submissions/{submission_id}/photos",
    response_model=PhotosUploadOut,
)
async def upload_photos(
    submission_id: int,
    start_seq: int = Query(..., description="Starting sequence number, e.g., 1"),
    images: List[UploadFile] = File(..., description="Upload multiple files with key 'images'"),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # ✅ Validate session/submission exists & belongs to student
    session_stmt = select(ActivitySession).where(
        ActivitySession.id == submission_id,
        ActivitySession.student_id == student.id,
    )
    session_res = await db.execute(session_stmt)
    session = session_res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Submission/Session not found for this student")

    results = []
    seq_no = start_seq

    for img in images:
        file_bytes = await img.read()
        if not file_bytes:
            continue

        # ✅ Store in MinIO (keep session_id = ActivitySession.id)
        image_url = await upload_activity_image(
            file_bytes=file_bytes,
            content_type=img.content_type or "application/octet-stream",
            filename=img.filename or f"photo_{seq_no}.jpg",
            student_id=student.id,
            session_id=session.id,
        )

        photo = await add_photo(
            db=db,
            submission_id=session.id,
            student_id=student.id,
            seq_no=seq_no,
            image_url=image_url,
        )

        results.append(photo)
        seq_no += 1

    # ✅ Return strongly-typed response
    return PhotosUploadOut(
        session_id=session.id,   # frontend should use this in /face/verify-session/{session_id}
        photos=results,
    )


@router.post("/student/submissions/{submission_id}/submit", response_model=SubmissionOut)
async def submit_event(
    submission_id: int,
    payload: FinalSubmitIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await final_submit(db, submission_id, student.id, payload.description)


# ---------------- ADMIN: REVIEW ----------------

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