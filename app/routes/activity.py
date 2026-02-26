# app/routes/activity.py

from __future__ import annotations

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Query,
    HTTPException,
    Form,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.dependencies import get_current_student, get_current_admin

from app.schemas.activity import (
    ActivityTypeOut,
    RequestActivityTypeIn,
    CreateSessionIn,
    SessionOut,
    PhotoOut,
    SubmitSessionOut,
    SessionListItemOut,
    SessionDetailOut,
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
from app.models.activity_photo import ActivityPhoto
from app.models.activity_session import ActivitySession, ActivitySessionStatus


# NOTE:
# These routers are typically included in main.py with prefix="/api"
# Example:
#   app.include_router(router, prefix="/api")
#   app.include_router(admin_router, prefix="/api")
#   app.include_router(legacy_router, prefix="/api")
router = APIRouter(prefix="/student/activity", tags=["Student - Activity"])
admin_router = APIRouter(prefix="/admin/activity", tags=["Admin - Activity"])
legacy_router = APIRouter(prefix="/student", tags=["Student - Legacy"])


# ─────────────────────────────────────────────────────────────
# Datetime parsing helper
# ─────────────────────────────────────────────────────────────
def _normalize_ddmmyyyy_date(date_part: str) -> str:
    parts = date_part.strip().split("/")
    if len(parts) != 3:
        return date_part.strip()
    d, m, y = parts
    return f"{d.zfill(2)}/{m.zfill(2)}/{y}"


def parse_captured_at(meta_captured_at: str):
    """
    Accepts:
      - ISO: 2026-02-26T11:39:49+05:30 / 2026-02-26T06:09:49Z
      - DD/MM/YYYY, hh:mm:ss am/pm  (example: 26/2/2026, 11:39:49 am)
      - DD/MM/YYYY hh:mm:ss am/pm
      - DD-MM-YYYY, hh:mm:ss am/pm
    If timezone missing, assumes Asia/Kolkata.
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo

    s = (meta_captured_at or "").strip()
    if not s:
        raise HTTPException(status_code=422, detail="meta_captured_at is required")

    # 1) Try ISO (supports Z)
    try:
        iso = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        return dt
    except ValueError:
        pass

    cleaned = s
    cleaned = cleaned.replace(" AM", " am").replace(" PM", " pm")
    cleaned = cleaned.replace(" a.m.", " am").replace(" p.m.", " pm")
    cleaned = cleaned.strip()

    if "," in cleaned:
        date_part, time_part = [x.strip() for x in cleaned.split(",", 1)]
    else:
        parts = cleaned.split()
        if len(parts) >= 2:
            date_part = parts[0].strip()
            time_part = " ".join(parts[1:]).strip()
        else:
            date_part, time_part = cleaned, ""

    date_part_norm = _normalize_ddmmyyyy_date(date_part)

    candidates = [
        f"{date_part_norm}, {time_part}".strip(),
        f"{date_part_norm} {time_part}".strip(),
        cleaned,
    ]

    fmts = [
        "%d/%m/%Y, %I:%M:%S %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%d/%m/%Y, %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y, %I:%M:%S %p",
        "%d-%m-%Y %I:%M:%S %p",
        "%d-%m-%Y, %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
    ]

    last_err = None
    for cand in candidates:
        if not cand:
            continue
        cand2 = cand.replace(" am", " AM").replace(" pm", " PM")
        for fmt in fmts:
            try:
                dt = datetime.strptime(cand2, fmt)
                dt = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
                return dt
            except ValueError as e:
                last_err = e

    raise HTTPException(
        status_code=422,
        detail={
            "message": "Invalid meta_captured_at format",
            "received": s,
            "expected_examples": [
                "2026-02-26T11:39:49+05:30",
                "2026-02-26T06:09:49Z",
                "26/2/2026, 11:39:49 am",
                "26/02/2026 11:39:49 AM",
            ],
            "error": str(last_err) if last_err else "unparseable",
        },
    )


# ─────────────────────────────────────────────────────────────
# seq_no helper
# ─────────────────────────────────────────────────────────────
async def _next_seq_no(db: AsyncSession, session_id: int) -> int:
    q = select(func.max(ActivityPhoto.seq_no)).where(ActivityPhoto.session_id == session_id)
    res = await db.execute(q)
    mx = res.scalar_one_or_none()
    return int(mx or 0) + 1


# ─────────────────────────────────────────────────────────────
# session pre-check helper (IMPORTANT: prevents MinIO waste)
# ─────────────────────────────────────────────────────────────
async def _assert_session_uploadable(db: AsyncSession, student_id: int, session_id: int):
    res = await db.execute(
        select(ActivitySession).where(
            ActivitySession.id == session_id,
            ActivitySession.student_id == student_id,
        )
    )
    session = res.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != ActivitySessionStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Cannot upload photos after submission")

    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    if session.expires_at and now > session.expires_at:
        session.status = ActivitySessionStatus.EXPIRED
        await db.commit()
        raise HTTPException(status_code=400, detail="Session expired")


# ─────────────────────────────────────────────────────────────
# Student - Activity
# ─────────────────────────────────────────────────────────────
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
    seq_no: int | None,
) -> PhotoOut:
    # 0) Validate session BEFORE upload (prevents wasted MinIO uploads)
    await _assert_session_uploadable(db, student_id, session_id)

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

    # 3) Parse captured_at (flexible)
    captured_at = parse_captured_at(meta_captured_at)

    # 4) Decide seq_no
    if seq_no is None:
        seq_no = await _next_seq_no(db, session_id)

    # 5) Save photo record
    return await add_photo_to_session(
        db=db,
        student_id=student_id,
        session_id=session_id,
        seq_no=seq_no,
        image_url=image_url,
        captured_at=captured_at,
        lat=lat,
        lng=lng,
        sha256=sha256,
    )


# IMPORTANT:
# React Native/Expo sometimes fails on POST redirects (307).
# So we accept BOTH /photos and /photos/ to eliminate redirect-slash issues.
@router.post("/sessions/{session_id}/photos", response_model=PhotoOut)
@router.post("/sessions/{session_id}/photos/", response_model=PhotoOut)
async def upload_activity_photo(
    session_id: int,
    seq_no: int | None = Query(
        None,
        ge=1,
        description="Photo sequence number (1..required_photos). If omitted, server auto-assigns next.",
    ),
    meta_captured_at: str = Query(..., description="ISO preferred; also accepts DD/MM/YYYY, hh:mm:ss am/pm"),
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
        seq_no=seq_no,
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


# ─────────────────────────────────────────────────────────────
# Admin - Activity
# ─────────────────────────────────────────────────────────────
@admin_router.get("/types", response_model=list[ActivityTypeOut])
async def admin_list_types(
    include_pending: bool = True,
    db: AsyncSession = Depends(get_db),
    admin=Depends(get_current_admin),
):
    return await list_activity_types(db, include_pending=include_pending)


# ─────────────────────────────────────────────────────────────
# Legacy compatibility route
# Frontend expects:
#   POST /api/student/submissions/{id}/photos?start_seq=1
# ─────────────────────────────────────────────────────────────
@legacy_router.post("/submissions/{submission_id}/photos", response_model=PhotoOut)
@legacy_router.post("/submissions/{submission_id}/photos/", response_model=PhotoOut)
async def legacy_upload_submission_photo(
    submission_id: int,
    start_seq: int = Query(1, ge=1),
    meta_captured_at: str | None = Query(None),
    captured_at: str | None = Query(None),
    lat: float | None = Query(None),
    lng: float | None = Query(None),
    latitude: float | None = Query(None),
    longitude: float | None = Query(None),
    sha256: str | None = Query(None),
    meta_captured_at_f: str | None = Form(None),
    captured_at_f: str | None = Form(None),
    lat_f: float | None = Form(None),
    lng_f: float | None = Form(None),
    latitude_f: float | None = Form(None),
    longitude_f: float | None = Form(None),
    sha256_f: str | None = Form(None),
    image: UploadFile | None = File(None),
    file: UploadFile | None = File(None),
    photo: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    student=Depends(get_current_student),
):
    cap = meta_captured_at or captured_at or meta_captured_at_f or captured_at_f

    lat_val = (
        lat
        if lat is not None
        else (latitude if latitude is not None else (lat_f if lat_f is not None else latitude_f))
    )
    lng_val = (
        lng
        if lng is not None
        else (longitude if longitude is not None else (lng_f if lng_f is not None else longitude_f))
    )

    sha = sha256 or sha256_f
    upload = image or file or photo

    if upload is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "image file missing. Send multipart/form-data with one of: image | file | photo",
                "expected": {"file_field": ["image", "file", "photo"]},
            },
        )

    if not cap:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "captured_at missing. Send one of: meta_captured_at | captured_at (query or form)",
                "expected": {"captured_at_field": ["meta_captured_at", "captured_at"]},
            },
        )

    if lat_val is None or lng_val is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "lat/lng missing. Send lat,lng or latitude,longitude (query or form)",
                "received": {"lat": lat_val, "lng": lng_val},
            },
        )

    # Validate session BEFORE upload
    await _assert_session_uploadable(db, student.id, submission_id)

    return await _handle_photo_upload_and_save(
        db=db,
        student_id=student.id,
        session_id=submission_id,
        meta_captured_at=cap,
        lat=float(lat_val),
        lng=float(lng_val),
        sha256=sha,
        image=upload,
        seq_no=int(start_seq),
    )