from fastapi import APIRouter, Depends, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin

from app.schemas.activity import (
    ActivityTypeOut,
    RequestActivityTypeIn,
    CreateSessionIn,
    SessionOut,
    PhotoOut,
    SubmitSessionOut,
)
from app.controllers.activity_controller import (
    list_activity_types,
    request_new_activity_type,
    create_session,
    add_photo_to_session,
    submit_session,
)

# ✅ Use your MinIO-style uploader (bytes -> url)
from app.core.activity_storage import upload_activity_image

router = APIRouter(prefix="/student/activity", tags=["Student - Activity"])


@router.get("/types", response_model=list[ActivityTypeOut])
async def get_types(db: AsyncSession = Depends(get_db)):
    return await list_activity_types(db, include_pending=False)


@router.post("/types/request", response_model=ActivityTypeOut)
async def request_type(
    payload: RequestActivityTypeIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await request_new_activity_type(db, payload.name, payload.description)


@router.post("/sessions", response_model=SessionOut)
async def create_activity_session(
    payload: CreateSessionIn,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await create_session(
        db,
        student.id,
        payload.activity_type_id,
        payload.activity_name,
        payload.description,
    )


@router.post("/sessions/{session_id}/photos", response_model=PhotoOut)
async def upload_activity_photo(
    session_id: int,
    meta_captured_at: str = Query(..., description="ISO datetime with timezone recommended"),
    lat: float = Query(...),
    lng: float = Query(...),
    sha256: str | None = Query(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # 1) Read bytes from upload
    file_bytes = await image.read()
    if not file_bytes:
        raise ValueError("Empty file")

    # 2) Upload to MinIO and get URL
    image_url = await upload_activity_image(
        file_bytes=file_bytes,
        content_type=image.content_type or "application/octet-stream",
        filename=image.filename or "photo.jpg",
        student_id=student.id,
        session_id=session_id,
    )

    # 3) Parse captured_at
    from datetime import datetime
    captured_at = datetime.fromisoformat(meta_captured_at)

    # 4) Save photo record
    return await add_photo_to_session(
        db=db,
        student_id=student.id,
        session_id=session_id,
        image_url=image_url,
        captured_at=captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
    )


@router.post("/sessions/{session_id}/submit", response_model=SubmitSessionOut)
async def submit_activity(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    session, newly, total_points, total_hours = await submit_session(db, student.id, session_id)
    return {
        "session": session,
        "newly_awarded_points": newly,
        "total_points_for_type": total_points,
        "total_hours_for_type": total_hours,
    }


# --- Admin routes (minimal) ---
admin_router = APIRouter(prefix="/admin/activity", tags=["Admin - Activity"])


@admin_router.get("/types", response_model=list[ActivityTypeOut])
async def admin_list_types(
    include_pending: bool = True,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await list_activity_types(db, include_pending=include_pending)