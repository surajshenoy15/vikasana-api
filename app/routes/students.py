from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.dependencies import get_current_faculty, get_current_admin, get_current_student
from app.models.faculty import Faculty
from app.models.admin import Admin
from app.models.student import Student

from app.schemas.student import StudentCreate, StudentOut, BulkUploadResult
from app.controllers.student_controller import create_student, create_students_from_csv

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
    current_faculty: Faculty = Depends(get_current_faculty),  # ✅ AUTH ENFORCED
):
    stmt = (
        select(Student)
        .options(selectinload(Student.created_by_faculty))  # ✅ load mentor
        .where(Student.college == current_faculty.college)  # ✅ scope to faculty college
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
    students = result.scalars().all()

    # ✅ Build response with mentor name
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
        )
        for s in students
    ]


@faculty_router.post("", response_model=StudentOut)
async def add_student_manual(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),
):
    try:
        # ✅ pass full faculty, not only college
        s = await create_student(db, payload, current_faculty=current_faculty)
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
        )
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@faculty_router.post("/bulk-upload", response_model=BulkUploadResult)
async def add_students_bulk(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="If true, existing USNs/emails (in same college) will be skipped"),
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
        faculty_id=current_faculty.id,  # ✅ NEW
    )

    return BulkUploadResult(
        total_rows=total,
        inserted=inserted,
        skipped_duplicates=skipped,
        invalid_rows=invalid,
        errors=errors,
    )


# ─────────────────────────────────────────────────────────────
# ADMIN ROUTES (LIST ONLY)
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
    stmt = select(Student).options(selectinload(Student.created_by_faculty))

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
    students = result.scalars().all()

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
        )
        for s in students
    ]


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