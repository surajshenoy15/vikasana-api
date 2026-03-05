# app/routes/students.py
# ✅ Fully updated to return REAL counts:
# - activities_count = COUNT(EventSubmission)  (your "activities" are event submissions)
# - certificates_count = COUNT(Certificate)

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from pydantic import BaseModel, Field, model_validator, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, func
from sqlalchemy.orm import selectinload
from app.models.student_point_adjustment import StudentPointAdjustment
from typing import Literal,Any
from app.core.database import get_db
from app.core.dependencies import get_current_faculty, get_current_admin, get_current_student
from app.models.faculty import Faculty
from app.models.admin import Admin
from app.models.student import Student, StudentType

# ✅ REAL sources for counts (matches your Certificate model)
from app.models.events import EventSubmission
from app.models.certificate import Certificate

from app.schemas.student import StudentCreate, StudentOut, BulkUploadResult
from app.controllers.student_controller import create_student, create_students_from_csv

from pydantic import BaseModel, EmailStr
from typing import Optional


# ─────────────────────────────────────────────────────────────
# SCHEMA (PATCH) - matches your Student model (NO is_active field)
# ─────────────────────────────────────────────────────────────
class StudentUpdate(BaseModel):
    college: Optional[str] = None
    name: Optional[str] = None
    usn: Optional[str] = None
    branch: Optional[str] = None
    email: Optional[EmailStr] = None
    student_type: Optional[str] = None  # REGULAR / DIPLOMA
    passout_year: Optional[int] = None
    admitted_year: Optional[int] = None


def _normalize_student_type(v: str | None) -> str | None:
    if v is None:
        return None
    v = str(v).strip().upper()
    if v not in (StudentType.REGULAR.value, StudentType.DIPLOMA.value):
        raise HTTPException(status_code=422, detail="student_type must be REGULAR or DIPLOMA")
    return v


# ─────────────────────────────────────────────────────────────
# FACULTY ROUTES
# ─────────────────────────────────────────────────────────────
faculty_router = APIRouter(prefix="/faculty/students", tags=["Faculty - Students"])


@faculty_router.get("", response_model=list[StudentOut])
async def list_students(
    q: str | None = Query(None, description="Optional search. Matches name/usn/branch/email."),
    student_type: str | None = Query(None, description="Optional filter: REGULAR or DIPLOMA"),
    branch: str | None = Query(None, description="Optional filter by branch (exact match)."),
    passout_year: int | None = Query(None, description="Optional filter by passout year."),
    admitted_year: int | None = Query(None, description="Optional filter by admitted year."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    # ✅ activities = event submissions
    activities_sq = (
        select(
            EventSubmission.student_id.label("student_id"),
            func.count(EventSubmission.id).label("activities_count"),
        )
        .group_by(EventSubmission.student_id)
        .subquery()
    )

    # ✅ certificates = certificates table
    certs_sq = (
        select(
            Certificate.student_id.label("student_id"),
            func.count(Certificate.id).label("certificates_count"),
        )
        .group_by(Certificate.student_id)
        .subquery()
    )

    stmt = (
        select(
            Student,
            func.coalesce(activities_sq.c.activities_count, 0).label("activities_count"),
            func.coalesce(certs_sq.c.certificates_count, 0).label("certificates_count"),
        )
        .options(selectinload(Student.created_by_faculty))
        .outerjoin(activities_sq, activities_sq.c.student_id == Student.id)
        .outerjoin(certs_sq, certs_sq.c.student_id == Student.id)
        .where(Student.college == current_faculty.college)
    )

    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Student.name.ilike(like),
                Student.usn.ilike(like),
                Student.branch.ilike(like),
                Student.email.ilike(like),
            )
        )

    if student_type and student_type.strip():
        stmt = stmt.where(Student.student_type == student_type.strip().upper())

    if branch and branch.strip():
        stmt = stmt.where(Student.branch == branch.strip())

    if passout_year is not None:
        stmt = stmt.where(Student.passout_year == passout_year)

    if admitted_year is not None:
        stmt = stmt.where(Student.admitted_year == admitted_year)

    stmt = stmt.order_by(Student.id.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        StudentOut(
            id=s.id,
            name=s.name,
            usn=s.usn,
            branch=s.branch,
            email=s.email,
            student_type=str(s.student_type),
            passout_year=s.passout_year,
            admitted_year=s.admitted_year,
            college=s.college,
            faculty_mentor_name=(s.created_by_faculty.full_name if s.created_by_faculty else None),
            activities_count=int(activities_count or 0),
            certificates_count=int(certificates_count or 0),
        )
        for (s, activities_count, certificates_count) in rows
    ]


@faculty_router.post("", response_model=StudentOut)
async def add_student_manual(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    try:
        s = await create_student(
            db,
            payload,
            faculty_college=current_faculty.college,
            faculty_id=current_faculty.id,
        )
        return StudentOut(
            id=s.id,
            name=s.name,
            usn=s.usn,
            branch=s.branch,
            email=s.email,
            student_type=str(s.student_type),
            passout_year=s.passout_year,
            admitted_year=s.admitted_year,
            college=s.college,
            faculty_mentor_name=(s.created_by_faculty.full_name if s.created_by_faculty else None),
            activities_count=0,
            certificates_count=0,
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@faculty_router.post("/bulk-upload", response_model=BulkUploadResult)
async def add_students_bulk(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="If true, existing USNs/emails will be skipped"),
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv file is allowed")

    data = await file.read()

    total, inserted, skipped, invalid, errors = await create_students_from_csv(
        db=db,
        csv_bytes=data,
        skip_duplicates=skip_duplicates,
        faculty_college=current_faculty.college,
        faculty_id=current_faculty.id,
    )

    return BulkUploadResult(
        total_rows=total,
        inserted=inserted,
        skipped_duplicates=skipped,
        invalid_rows=invalid,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────
# ADMIN ROUTES (LIST + GET BY ID + PATCH)
# ─────────────────────────────────────────────────────────────
admin_router = APIRouter(prefix="/admin/students", tags=["Admin - Students"])


@admin_router.get("", response_model=list[StudentOut])
async def list_students_admin(
    q: str | None = Query(None, description="Optional search. Matches name/usn/branch/email."),
    college: str | None = Query(None, description="Optional filter by college (exact match)."),
    student_type: str | None = Query(None, description="Optional filter: REGULAR or DIPLOMA"),
    branch: str | None = Query(None, description="Optional filter by branch (exact match)."),
    passout_year: int | None = Query(None, description="Optional filter by passout year."),
    admitted_year: int | None = Query(None, description="Optional filter by admitted year."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    activities_sq = (
        select(
            EventSubmission.student_id.label("student_id"),
            func.count(EventSubmission.id).label("activities_count"),
        )
        .group_by(EventSubmission.student_id)
        .subquery()
    )

    certs_sq = (
        select(
            Certificate.student_id.label("student_id"),
            func.count(Certificate.id).label("certificates_count"),
        )
        .group_by(Certificate.student_id)
        .subquery()
    )

    stmt = (
        select(
            Student,
            func.coalesce(activities_sq.c.activities_count, 0).label("activities_count"),
            func.coalesce(certs_sq.c.certificates_count, 0).label("certificates_count"),
        )
        .options(selectinload(Student.created_by_faculty))
        .outerjoin(activities_sq, activities_sq.c.student_id == Student.id)
        .outerjoin(certs_sq, certs_sq.c.student_id == Student.id)
    )

    if college and college.strip():
        stmt = stmt.where(Student.college == college.strip())

    if q and q.strip():
        like = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Student.name.ilike(like),
                Student.usn.ilike(like),
                Student.branch.ilike(like),
                Student.email.ilike(like),
            )
        )

    if student_type and student_type.strip():
        stmt = stmt.where(Student.student_type == student_type.strip().upper())

    if branch and branch.strip():
        stmt = stmt.where(Student.branch == branch.strip())

    if passout_year is not None:
        stmt = stmt.where(Student.passout_year == passout_year)

    if admitted_year is not None:
        stmt = stmt.where(Student.admitted_year == admitted_year)

    stmt = stmt.order_by(Student.id.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    rows = result.all()

    return [
        StudentOut(
            id=s.id,
            name=s.name,
            usn=s.usn,
            branch=s.branch,
            email=s.email,
            student_type=str(s.student_type),
            passout_year=s.passout_year,
            admitted_year=s.admitted_year,
            college=s.college,
            faculty_mentor_name=(s.created_by_faculty.full_name if s.created_by_faculty else None),
            activities_count=int(activities_count or 0),
            certificates_count=int(certificates_count or 0),
        )
        for (s, activities_count, certificates_count) in rows
    ]


@admin_router.get("/{student_id}", response_model=StudentOut)
async def get_student_admin(
    student_id: int,
    db: AsyncSession = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    activities_count_sq = (
        select(func.count(EventSubmission.id))
        .where(EventSubmission.student_id == student_id)
        .scalar_subquery()
    )

    certificates_count_sq = (
        select(func.count(Certificate.id))
        .where(Certificate.student_id == student_id)
        .scalar_subquery()
    )

    stmt = (
        select(
            Student,
            func.coalesce(activities_count_sq, 0).label("activities_count"),
            func.coalesce(certificates_count_sq, 0).label("certificates_count"),
        )
        .options(selectinload(Student.created_by_faculty))
        .where(Student.id == student_id)
    )

    res = await db.execute(stmt)
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Student not found")

    s, activities_count, certificates_count = row

    return StudentOut(
        id=s.id,
        name=s.name,
        usn=s.usn,
        branch=s.branch,
        email=s.email,
        student_type=str(s.student_type),
        passout_year=s.passout_year,
        admitted_year=s.admitted_year,
        college=s.college,
        faculty_mentor_name=(s.created_by_faculty.full_name if s.created_by_faculty else None),
        activities_count=int(activities_count or 0),
        certificates_count=int(certificates_count or 0),
    )


@admin_router.patch("/{student_id}", response_model=StudentOut)
async def update_student_admin(
    student_id: int,
    payload: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    res = await db.execute(
        select(Student)
        .options(selectinload(Student.created_by_faculty))
        .where(Student.id == student_id)
    )
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")

    data = payload.model_dump(exclude_unset=True)

    # normalize fields
    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
    if "college" in data and data["college"] is not None:
        data["college"] = str(data["college"]).strip()
    if "usn" in data and data["usn"] is not None:
        data["usn"] = str(data["usn"]).strip()
    if "branch" in data and data["branch"] is not None:
        data["branch"] = str(data["branch"]).strip()
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).strip().lower()
    if "student_type" in data:
        data["student_type"] = _normalize_student_type(data.get("student_type"))

    # uniqueness checks (your DB constraints are GLOBAL)
    if "usn" in data and data["usn"]:
        dup = await db.execute(
            select(Student.id).where(Student.usn == data["usn"], Student.id != s.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="USN already exists")

    if "email" in data and data["email"]:
        dup = await db.execute(
            select(Student.id).where(Student.email == data["email"], Student.id != s.id)
        )
        if dup.scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already exists")

    # apply updates
    for k, v in data.items():
        if v is None:
            continue
        setattr(s, k, v)

    await db.commit()
    await db.refresh(s)

    act_res = await db.execute(
        select(func.count(EventSubmission.id)).where(EventSubmission.student_id == s.id)
    )
    activities_count = act_res.scalar() or 0

    cert_res = await db.execute(
        select(func.count(Certificate.id)).where(Certificate.student_id == s.id)
    )
    certificates_count = cert_res.scalar() or 0

    return StudentOut(
        id=s.id,
        name=s.name,
        usn=s.usn,
        branch=s.branch,
        email=s.email,
        student_type=str(s.student_type),
        passout_year=s.passout_year,
        admitted_year=s.admitted_year,
        college=s.college,
        faculty_mentor_name=(s.created_by_faculty.full_name if s.created_by_faculty else None),
        activities_count=int(activities_count),
        certificates_count=int(certificates_count),
    )

class ManualActivityPointsIn(BaseModel):
    """
    Accepts both payload styles:

    1) Set total:
        { "mode": "SET_TOTAL", "new_total": 25, "reason": "..." }

    2) Add/Subtract:
        { "mode": "ADD_SUBTRACT", "delta": 5, "reason": "..." }
        { "mode": "ADD", "delta": 5, "reason": "..." }
        { "mode": "SUBTRACT", "delta": 5, "reason": "..." }

    Also supports legacy:
        { "mode": "...", "value": 25, "reason": "..." }
    """
    model_config = ConfigDict(extra="allow")

    mode: str = Field(..., description="SET_TOTAL | ADD_SUBTRACT | ADD | SUBTRACT")
    reason: str = Field(..., min_length=1)

    # frontend-friendly fields
    new_total: Optional[int] = None
    delta: Optional[int] = None

    # legacy support
    value: Optional[int] = None

    @model_validator(mode="before")
    @classmethod
    def normalize(cls, data: Any):
        if not isinstance(data, dict):
            return data

        # normalize mode values coming from UI labels
        m = str(data.get("mode", "")).strip().upper()
        if m in ("ADD / SUBTRACT", "ADD_SUBTRACT", "ADD-SUBTRACT"):
            m = "ADD_SUBTRACT"
        elif m in ("SET TOTAL", "SET_TOTAL"):
            m = "SET_TOTAL"
        data["mode"] = m

        # if frontend sends "value" for set total, map it
        if data.get("new_total") is None and data.get("value") is not None:
            data["new_total"] = data.get("value")

        # if frontend sends "value" for delta, map it
        if data.get("delta") is None and data.get("value") is not None and m in ("ADD", "SUBTRACT", "ADD_SUBTRACT"):
            data["delta"] = data.get("value")

        return data


@admin_router.patch("/{student_id}/activity-points")
async def admin_update_student_activity_points(
    student_id: int,
    payload: ManualActivityPointsIn,
    db: AsyncSession = Depends(get_db),
    current_admin: Admin = Depends(get_current_admin),
):
    # ✅ IMPORTANT: lock ONLY student row (NO joins / no selectinload here)
    res = await db.execute(
        select(Student).where(Student.id == student_id).with_for_update()
    )
    s = res.scalar_one_or_none()
    if not s:
        raise HTTPException(status_code=404, detail="Student not found")

    old_total = int(s.total_points_earned or 0)
    mode = (payload.mode or "").strip().upper()

    if mode == "SET_TOTAL":
        if payload.new_total is None:
            raise HTTPException(status_code=422, detail="new_total is required for SET_TOTAL")
        new_total = int(payload.new_total)
        delta = new_total - old_total

    elif mode in ("ADD_SUBTRACT", "ADD", "SUBTRACT"):
        if payload.delta is None:
            raise HTTPException(status_code=422, detail="delta is required for ADD/SUBTRACT")
        d = int(payload.delta)

        if mode == "SUBTRACT":
            d = -abs(d)
        elif mode == "ADD":
            d = abs(d)
        # ADD_SUBTRACT keeps sign as given

        delta = d
        new_total = old_total + delta

    else:
        raise HTTPException(status_code=422, detail="mode must be SET_TOTAL | ADD_SUBTRACT | ADD | SUBTRACT")

    if new_total < 0:
        raise HTTPException(status_code=422, detail="total points cannot be negative")

    s.total_points_earned = int(new_total)

    db.add(
        StudentPointAdjustment(
            student_id=s.id,
            delta_points=int(delta),
            new_total_points=int(new_total),
            reason=payload.reason.strip(),
            created_by_admin_id=getattr(current_admin, "id", None),
        )
    )

    await db.commit()

    return {
        "student_id": s.id,
        "old_total": old_total,
        "new_total": int(new_total),
        "delta": int(delta),
    }# ─────────────────────────────────────────────────────────────
# STUDENT ROUTES (PROFILE)
# ─────────────────────────────────────────────────────────────
student_router = APIRouter(prefix="/students", tags=["Student - Profile"])


@student_router.get("/me")
async def get_student_me(
    current_student: Student = Depends(get_current_student),
):
    return {
        "id": current_student.id,
        "name": current_student.name,
        "email": current_student.email,
        "college": current_student.college,
        "usn": current_student.usn,
        "branch": current_student.branch,
        "face_enrolled": current_student.face_enrolled,
        "face_enrolled_at": current_student.face_enrolled_at,
        "required_total_points": current_student.required_total_points,
        "total_points_earned": current_student.total_points_earned,
    }