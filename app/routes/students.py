from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_

from app.core.database import get_db
from app.core.dependencies import get_current_faculty
from app.models.faculty import Faculty
from app.models.student import Student

from app.schemas.student import StudentCreate, StudentOut, BulkUploadResult
from app.controllers.student_controller import create_student, create_students_from_csv

router = APIRouter(prefix="/faculty/students", tags=["Faculty - Students"])


@router.get("", response_model=list[StudentOut])
async def list_students(
    q: str | None = Query(
        None,
        description="Optional search. Matches name/usn/branch/email.",
    ),
    student_type: str | None = Query(
        None,
        description="Optional filter: REGULAR or DIPLOMA",
    ),
    branch: str | None = Query(
        None,
        description="Optional filter by branch (exact match).",
    ),
    passout_year: int | None = Query(None, description="Optional filter by passout year."),
    admitted_year: int | None = Query(None, description="Optional filter by admitted year."),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),  # ✅ AUTH ENFORCED
):
    stmt = select(Student)

    # Search
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

    # Filters
    if student_type and student_type.strip():
        # Stored as enum in DB; comparing with string works fine in SQLAlchemy
        stmt = stmt.where(Student.student_type == student_type.strip().upper())

    if branch and branch.strip():
        stmt = stmt.where(Student.branch == branch.strip())

    if passout_year is not None:
        stmt = stmt.where(Student.passout_year == passout_year)

    if admitted_year is not None:
        stmt = stmt.where(Student.admitted_year == admitted_year)

    stmt = stmt.order_by(Student.id.desc()).limit(limit).offset(offset)

    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("", response_model=StudentOut)
async def add_student_manual(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),  # ✅ AUTH ENFORCED
):
    try:
        return await create_student(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/bulk-upload", response_model=BulkUploadResult)
async def add_students_bulk(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="If true, existing USNs will be skipped"),
    db: AsyncSession = Depends(get_db),
    current_faculty: Faculty = Depends(get_current_faculty),  # ✅ AUTH ENFORCED
):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv file is allowed")

    data = await file.read()

    total, inserted, skipped, invalid, errors = await create_students_from_csv(
        db=db,
        csv_bytes=data,
        skip_duplicates=skip_duplicates,
    )

    return BulkUploadResult(
        total_rows=total,
        inserted=inserted,
        skipped_duplicates=skipped,
        invalid_rows=invalid,
        errors=errors,
    )