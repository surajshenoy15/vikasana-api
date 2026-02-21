from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.student import StudentCreate, StudentOut, BulkUploadResult
from app.controllers.student_controller import create_student, create_students_from_csv

# ✅ adjust this import based on your project
from app.core.database import get_async_session  # or wherever your DB dependency is

# ✅ adjust based on your auth system (faculty-only)
from app.routes.auth import get_current_user  # OR app.core.security import get_current_user
from app.models.faculty import Faculty


router = APIRouter(prefix="/faculty/students", tags=["Faculty - Students"])


def _ensure_faculty(user):
    # If your get_current_user returns Faculty/Admin etc, enforce faculty here.
    # Adjust this logic according to your auth payload
    if not isinstance(user, Faculty):
        raise HTTPException(status_code=403, detail="Only faculty can manage students")


@router.post("", response_model=StudentOut)
async def add_student_manual(
    payload: StudentCreate,
    db: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    _ensure_faculty(user)
    try:
        return await create_student(db, payload)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/bulk-upload", response_model=BulkUploadResult)
async def add_students_bulk(
    file: UploadFile = File(...),
    skip_duplicates: bool = Query(True, description="If true, existing USNs will be skipped"),
    db: AsyncSession = Depends(get_async_session),
    user=Depends(get_current_user),
):
    _ensure_faculty(user)

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