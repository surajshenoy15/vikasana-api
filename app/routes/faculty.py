from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, desc
import csv
import io

from app.core.database import get_db
from app.core.dependencies import get_current_admin, get_current_faculty

from app.models.admin import Admin
from app.models.faculty import Faculty
from app.models.student import Student

# ✅ activity session models
from app.models.activity_session import ActivitySession

# If you have an enum for status, import it safely
try:
    from app.models.activity_session import ActivitySessionStatus  # type: ignore
except Exception:
    ActivitySessionStatus = None  # fallback

from app.schemas.faculty import (
    FacultyCreateResponse,
    FacultyResponse,
    ActivateFacultyResponse,
    FacultyCreateRequest,
)

from app.schemas.faculty_import import FacultyImportResponse, FailedRow

from app.schemas.faculty_activation import (
    ActivationValidateResponse,
    SendOtpRequest,
    VerifyOtpRequest,
    VerifyOtpResponse,
    SetPasswordRequest,
    SetPasswordResponse,
)

from app.controllers.faculty_controller import (
    create_faculty,
    validate_activation_token_and_create_session,
    send_activation_otp,
    verify_activation_otp,
    set_password_after_otp,
    activate_faculty,
)

router = APIRouter(prefix="/faculty", tags=["Faculty"])


# =========================================================
# ADMIN ONLY: CREATE / LIST / DELETE FACULTY
# =========================================================

@router.post(
    "",
    response_model=FacultyCreateResponse,
    summary="Create Faculty (Admin only)",
)
async def add_faculty(
    full_name: str = Form(...),
    college: str = Form(...),
    email: str = Form(...),
    role: str = Form("faculty"),
    image: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    payload = FacultyCreateRequest(full_name=full_name, college=college, email=email, role=role)

    image_bytes = None
    if image:
        image_bytes = await image.read()

    faculty, email_sent = await create_faculty(
        payload=payload,
        db=db,
        image_bytes=image_bytes,
        image_content_type=image.content_type if image else None,
        image_filename=image.filename if image else None,
    )

    message = (
        "Faculty created and activation email sent."
        if email_sent
        else "Faculty created, but activation email could not be sent (email not configured)."
    )

    return {
        "faculty": FacultyResponse.model_validate(faculty),
        "activation_email_sent": email_sent,
        "message": message,
    }


@router.post(
    "/import-csv",
    response_model=FacultyImportResponse,
    summary="Import Faculty via CSV (Admin only)",
)
async def import_faculty_csv(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")

    raw = await file.read()
    try:
        text = raw.decode("utf-8-sig")  # handles BOM
    except Exception:
        raise HTTPException(status_code=400, detail="CSV must be UTF-8 encoded")

    reader = csv.DictReader(io.StringIO(text))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV has no header row")

    required = {"full_name", "email", "college", "role"}
    headers = {h.strip() for h in reader.fieldnames if h}
    missing = required - headers
    if missing:
        raise HTTPException(status_code=400, detail=f"Missing columns: {', '.join(sorted(missing))}")

    created_faculty: list[FacultyResponse] = []
    failed_rows: list[FailedRow] = []
    created_count = 0
    email_sent_count = 0

    # CSV header is row 1
    row_number = 1

    for row in reader:
        row_number += 1
        try:
            full_name = (row.get("full_name") or "").strip()
            email = (row.get("email") or "").strip().lower()
            college = (row.get("college") or "").strip()
            role = (row.get("role") or "faculty").strip() or "faculty"

            if not full_name:
                raise ValueError("full_name is required")
            if not email or "@" not in email:
                raise ValueError("valid email is required")
            if not college:
                raise ValueError("college is required")

            # prevent duplicates
            existing = await db.execute(select(Faculty).where(Faculty.email == email))
            if existing.scalar_one_or_none():
                raise ValueError("email already exists")

            payload = FacultyCreateRequest(
                full_name=full_name,
                college=college,
                email=email,
                role=role,
            )

            faculty, email_sent = await create_faculty(
                payload=payload,
                db=db,
                image_bytes=None,
                image_content_type=None,
                image_filename=None,
            )

            created_faculty.append(FacultyResponse.model_validate(faculty))
            created_count += 1
            if email_sent:
                email_sent_count += 1

        except Exception as e:
            failed_rows.append(FailedRow(row_number=row_number, error=str(e)))

    return FacultyImportResponse(
        created_count=created_count,
        failed_count=len(failed_rows),
        activation_email_sent_count=email_sent_count,
        failed_rows=failed_rows,
        created_faculty=created_faculty,
    )


@router.get(
    "",
    response_model=list[FacultyResponse],
    summary="List faculty (Admin only)",
)
async def list_faculty(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    q = await db.execute(select(Faculty).order_by(Faculty.created_at.desc()))
    items = q.scalars().all()
    return [FacultyResponse.model_validate(x) for x in items]


@router.delete("/{faculty_id}", summary="Delete faculty member (Admin only)")
async def delete_faculty(
    faculty_id: int,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(Faculty).where(Faculty.id == faculty_id))
    faculty = result.scalar_one_or_none()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await db.delete(faculty)
    await db.commit()
    return {"detail": f"Faculty {faculty_id} deleted"}


# =========================================================
# FACULTY APP: DASHBOARD STATS (keys match frontend)
# GET /api/faculty/dashboard/stats
# =========================================================

@router.get("/dashboard/stats", summary="Faculty dashboard stats (Faculty auth)")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    students = await db.scalar(
        select(func.count())
        .select_from(Student)
        .where(Student.college == current_faculty.college)
    )

    return {
        "students": int(students or 0),
        "verified": 0,
        "pending": 0,
        "rejected": 0,
    }


# =========================================================
# ✅ FACULTY APP: LIST ACTIVITY SESSIONS (Activities Tab)
# GET /api/faculty/activity-sessions
# =========================================================

@router.get("/activity-sessions", summary="List activity sessions (Faculty auth)")
async def list_activity_sessions(
    q: str | None = Query(None, description="Search by student name/usn/activity name"),
    status: str | None = Query(None, description="pending/approved/rejected"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    stmt = (
        select(ActivitySession, Student)
        .join(Student, Student.id == ActivitySession.student_id)
        .where(Student.college == current_faculty.college)
        .order_by(desc(ActivitySession.created_at))
        .limit(limit)
        .offset(offset)
    )

    if q:
        qq = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Student.name).like(qq),
                func.lower(Student.usn).like(qq),
                func.lower(func.coalesce(getattr(ActivitySession, "activity_name", None), "")).like(qq),
                func.lower(func.coalesce(getattr(ActivitySession, "title", None), "")).like(qq),
            )
        )

    if status:
        s = status.strip().lower()
        if s in ("pending", "approved", "rejected"):
            if ActivitySessionStatus:
                stmt = stmt.where(ActivitySession.status == ActivitySessionStatus[s.upper()])
            else:
                stmt = stmt.where(func.lower(ActivitySession.status) == s)

    rows = (await db.execute(stmt)).all()

    activities = []
    for sess, stu in rows:
        activities.append(
            {
                "id": sess.id,
                "title": getattr(sess, "activity_name", None)
                        or getattr(sess, "title", None)
                        or "Activity",
                "student_name": stu.name,
                "usn": stu.usn,
                "category": getattr(sess, "category", None) or getattr(sess, "activity_type", None),
                "description": getattr(sess, "description", None),
                "status": str(getattr(sess, "status", "pending")).lower(),
                "submitted_at": getattr(sess, "submitted_at", None) or getattr(sess, "created_at", None),
            }
        )

    return {"activities": activities, "count": len(activities)}


# =========================================================
# ✅ FACULTY APP: UPDATE STATUS (Approve/Reject)
# PATCH /api/faculty/activity-sessions/{session_id}/status
# Body: {"status":"approved"} / {"status":"rejected"}
# =========================================================

@router.patch("/activity-sessions/{session_id}/status", summary="Update activity session status (Faculty auth)")
async def update_activity_session_status(
    session_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    new_status = (body.get("status") or "").strip().lower()
    if new_status not in ("pending", "approved", "rejected"):
        raise HTTPException(status_code=400, detail="status must be one of: pending, approved, rejected")

    q = await db.execute(
        select(ActivitySession, Student)
        .join(Student, Student.id == ActivitySession.student_id)
        .where(ActivitySession.id == session_id)
    )
    row = q.first()
    if not row:
        raise HTTPException(status_code=404, detail="Activity session not found")

    sess, stu = row

    # Ensure faculty can update only their college students
    if (stu.college or "") != (current_faculty.college or ""):
        raise HTTPException(status_code=403, detail="Not allowed")

    # set status (enum or string)
    if ActivitySessionStatus:
        sess.status = ActivitySessionStatus[new_status.upper()]
    else:
        sess.status = new_status

    await db.commit()
    await db.refresh(sess)

    return {"detail": "Status updated", "id": sess.id, "status": str(sess.status).lower()}


# =========================================================
# ✅ NEW ACTIVATION FLOW (OTP + Set Password)
# =========================================================

@router.get(
    "/activation/validate",
    response_model=ActivationValidateResponse,
    summary="Validate activation token and create activation session",
)
async def activation_validate(
    token: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    session_id, email_masked, expires_at = await validate_activation_token_and_create_session(token, db)
    return {
        "activation_session_id": session_id,
        "email_masked": email_masked,
        "expires_at": expires_at,
    }


@router.post(
    "/activation/send-otp",
    summary="Send OTP to faculty email",
)
async def activation_send_otp(
    body: SendOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    await send_activation_otp(body.activation_session_id, db)
    return {"detail": "OTP sent successfully"}


@router.post(
    "/activation/verify-otp",
    response_model=VerifyOtpResponse,
    summary="Verify OTP and return set password token",
)
async def activation_verify_otp(
    body: VerifyOtpRequest,
    db: AsyncSession = Depends(get_db),
):
    set_password_token = await verify_activation_otp(body.activation_session_id, body.otp, db)
    return {"set_password_token": set_password_token}


@router.post(
    "/activation/set-password",
    response_model=SetPasswordResponse,
    summary="Set password after OTP verification",
)
async def activation_set_password(
    body: SetPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    await set_password_after_otp(body.set_password_token, body.new_password, db)
    return {"detail": "Password set successfully. Account activated."}


# =========================================================
# OPTIONAL: OLD ACTIVATE ENDPOINT (not recommended)
# =========================================================

@router.get(
    "/activate",
    response_model=ActivateFacultyResponse,
    summary="(OLD) Activate faculty account via email token (no OTP)",
)
async def activate(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    await activate_faculty(token, db)
    return {"detail": "Account activated successfully."}