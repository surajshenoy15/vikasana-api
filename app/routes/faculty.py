from fastapi import APIRouter, Depends, UploadFile, File, Form, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.admin import Admin
from app.models.faculty import Faculty
from app.schemas.faculty import (
    FacultyCreateResponse,
    FacultyResponse,
    ActivateFacultyResponse,
    FacultyCreateRequest,
)
from app.controllers.faculty_controller import create_faculty, activate_faculty

router = APIRouter(prefix="/faculty", tags=["Faculty"])


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

@router.delete("/{faculty_id}", summary="Delete faculty member")
async def delete_faculty(
    faculty_id: int,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    from sqlalchemy import select
    from app.models.faculty import Faculty
    result = await db.execute(select(Faculty).where(Faculty.id == faculty_id))
    faculty = result.scalar_one_or_none()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")
    await db.delete(faculty)
    await db.commit()
    return {"detail": f"Faculty {faculty_id} deleted"}
@router.get(
    "/activate",
    response_model=ActivateFacultyResponse,
    summary="Activate faculty account via email token",
)
async def activate(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    await activate_faculty(token, db)
    return {"detail": "Account activated successfully."}