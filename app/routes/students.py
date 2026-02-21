from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_faculty
from app.models.faculty import Faculty

from app.schemas.student import StudentCreate, StudentOut, BulkUploadResult
from app.controllers.student_controller import create_student, create_students_from_csv


router = APIRouter(prefix="/faculty/students", tags=["Faculty - Students"])


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