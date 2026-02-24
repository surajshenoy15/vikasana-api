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


@router.post("/student/submissions/{submission_id}/photos", response_model=PhotoOut)
async def upload_photo(
    submission_id: int,
    seq_no: int = Query(...),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    file_bytes = await image.read()

    image_url = await upload_activity_image(
        file_bytes=file_bytes,
        content_type=image.content_type,
        filename=image.filename,
        student_id=student.id,
        session_id=submission_id,
    )

    return await add_photo(
        db,
        submission_id=submission_id,
        student_id=student.id,
        seq_no=seq_no,
        image_url=image_url,
    )


@router.post("/student/submissions/{submission_id}/submit", response_model=SubmissionOut)
async def submit_event(
    submission_id: int,
    payload: FinalSubmitIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await final_submit(db, submission_id, student.id, payload.description)