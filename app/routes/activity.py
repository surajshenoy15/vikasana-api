from fastapi import APIRouter, Depends, UploadFile, File, Query, HTTPException
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
    list_student_sessions,
    get_student_session_detail,
)

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


async def _handle_photo_upload_and_save(
    *,
    db: AsyncSession,
    student_id: int,
    session_id: int,
    meta_captured_at: str,
    lat: float,
    lng: float,
    sha256: str | None,
    image: UploadFile,
) -> PhotoOut:
    # 1) Read bytes
    file_bytes = await image.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # 2) Upload to MinIO and get URL
    image_url = await upload_activity_image(
        file_bytes=file_bytes,
        content_type=image.content_type or "application/octet-stream",
        filename=image.filename or "photo.jpg",
        student_id=student_id,
        session_id=session_id,
    )

    # 3) Parse captured_at (accept Z)
    from datetime import datetime

    s = (meta_captured_at or "").strip()
    if not s:
        raise HTTPException(status_code=422, detail="meta_captured_at is required")

    s = s.replace("Z", "+00:00")
    captured_at = datetime.fromisoformat(s)

    # 4) Save photo record (upsert handled in controller)
    return await add_photo_to_session(
        db=db,
        student_id=student_id,
        session_id=session_id,
        image_url=image_url,
        captured_at=captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
    )


# ✅ Primary endpoint (your current one)
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
    return await _handle_photo_upload_and_save(
        db=db,
        student_id=student.id,
        session_id=session_id,
        meta_captured_at=meta_captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
        image=image,
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


from app.schemas.activity import SessionListItemOut, SessionDetailOut


@router.get("/sessions", response_model=list[SessionListItemOut])
async def my_sessions(
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await list_student_sessions(db, student.id)


@router.get("/sessions/{session_id}", response_model=SessionDetailOut)
async def session_detail(
    session_id: int,
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    return await get_student_session_detail(db, student.id, session_id)


# ============================================================
# ✅ COMPATIBILITY ROUTER (ALIAS) FOR YOUR FRONTEND CALL
# Frontend expects:
#   POST /api/student/submissions/{id}/photos?start_seq=1
# We'll provide:
#   POST /api/student/submissions/{submission_id}/photos
# that forwards to the same logic.
# ============================================================

legacy_router = APIRouter(prefix="/student", tags=["Student - Legacy"])


@legacy_router.post("/submissions/{submission_id}/photos", response_model=PhotoOut)
async def legacy_upload_submission_photo(
    submission_id: int,
    start_seq: int = Query(1, ge=1),  # accepted but not required by backend
    meta_captured_at: str = Query(..., description="ISO datetime"),
    lat: float = Query(...),
    lng: float = Query(...),
    sha256: str | None = Query(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # NOTE: start_seq is ignored unless you want to map it to seq_no.
    # Your controller uses UNIQUE(session_id, seq_no). If you want seq_no support,
    # update add_photo_to_session to accept seq_no.
    return await _handle_photo_upload_and_save(
        db=db,
        student_id=student.id,
        session_id=submission_id,
        meta_captured_at=meta_captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
        image=image,
    )

# ------------------------------------------------------------
# Legacy routes (to support older frontend URLs)
# ------------------------------------------------------------
legacy_router = APIRouter(prefix="/student", tags=["Student - Legacy"])


@legacy_router.post("/submissions/{submission_id}/photos", response_model=PhotoOut)
async def legacy_upload_submission_photo(
    submission_id: int,
    start_seq: int = Query(1, ge=1),
    meta_captured_at: str = Query(..., description="ISO datetime with timezone recommended"),
    lat: float = Query(...),
    lng: float = Query(...),
    sha256: str | None = Query(None),
    image: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    # reuse the existing endpoint logic
    return await upload_activity_photo(
        session_id=submission_id,
        meta_captured_at=meta_captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
        image=image,
        db=db,
        student=student,
    )