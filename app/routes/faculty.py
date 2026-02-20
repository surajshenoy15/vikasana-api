from fastapi import APIRouter, Depends, UploadFile, File, Form, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.admin import Admin
from app.schemas.faculty import FacultyCreateResponse, FacultyResponse, ActivateFacultyResponse
from app.schemas.faculty import FacultyCreateRequest
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

    faculty = await create_faculty(
        payload=payload,
        db=db,
        image_bytes=image_bytes,
        image_content_type=image.content_type if image else None,
        image_filename=image.filename if image else None,
    )

    return {
        "faculty": FacultyResponse.model_validate(faculty),
        "message": "Faculty created and activation email sent.",
    }


@router.get(
    "/activate",
    response_model=ActivateFacultyResponse,
    summary="Activate faculty account via email token",
)
async def activate(token: str = Query(...), db: AsyncSession = Depends(get_db)):
    await activate_faculty(token, db)
    return {"detail": "Account activated successfully."}