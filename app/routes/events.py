from typing import List

from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin
from app.core.activity_storage import upload_activity_image

from app.schemas.events import (
    EventCreateIn, EventOut,
    RegisterOut, PhotoOut,
    FinalSubmitIn, SubmissionOut
)

from app.controllers.events_controller import (
    create_event,
    list_active_events,
    register_for_event,
    add_photo,
    final_submit,
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
@router.post("/student/submissions/{submission_id}/photos", response_model=list[PhotoOut])
async def upload_photos(
    submission_id: int,
    start_seq: int = Query(..., description="Starting sequence number, e.g., 1"),
    images: List[UploadFile] = File(..., description="Upload multiple files with key 'images'"),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    results: list[PhotoOut] = []
    seq_no = start_seq

    for img in images:
        file_bytes = await img.read()
        if not file_bytes:
            continue

        image_url = await upload_activity_image(
            file_bytes=file_bytes,
            content_type=img.content_type or "application/octet-stream",
            filename=img.filename or f"photo_{seq_no}.jpg",
            student_id=student.id,
            session_id=submission_id,
        )

        photo = await add_photo(
            db=db,
            submission_id=submission_id,
            student_id=student.id,
            seq_no=seq_no,
            image_url=image_url,
        )

        results.append(photo)
        seq_no += 1

    return results


@router.post("/student/submissions/{submission_id}/submit", response_model=SubmissionOut)
async def submit_event(
    submission_id: int,
    payload: FinalSubmitIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await final_submit(db, submission_id, student.id, payload.description)