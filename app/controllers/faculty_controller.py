import os
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.models.faculty import Faculty
from app.schemas.faculty import FacultyCreateRequest
from app.core.file_storage import upload_faculty_image
from app.core.email_service import send_activation_email
from app.core.faculty_tokens import (
    create_activation_token,
    hash_token,
    verify_token,
    activation_expiry_dt,
)


async def create_faculty(
    payload: FacultyCreateRequest,
    db: AsyncSession,
    image_bytes: bytes | None = None,
    image_content_type: str | None = None,
    image_filename: str | None = None,
) -> tuple[Faculty, bool]:
    # check existing
    q = await db.execute(select(Faculty).where(Faculty.email == payload.email))
    existing = q.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="Faculty already exists with this email")

    image_url = None
    if image_bytes and image_filename:
        image_url = await upload_faculty_image(
            file_bytes=image_bytes,
            content_type=image_content_type or "image/jpeg",
            filename=image_filename,
        )

    token = create_activation_token(payload.email)
    token_hash = hash_token(token)

    faculty = Faculty(
        full_name=payload.full_name,
        college=payload.college,
        email=payload.email,
        role=payload.role,
        is_active=False,
        activation_token_hash=token_hash,
        activation_expires_at=activation_expiry_dt(),
        image_url=image_url,
    )

    db.add(faculty)
    await db.commit()
    await db.refresh(faculty)

    # activation URL (frontend page) OR API activation endpoint
    frontend_base = os.getenv("FRONTEND_BASE_URL", "").rstrip("/")
    # api_base is optional; keeping for future use
    api_base = os.getenv("API_BASE_URL", "").rstrip("/")

    if frontend_base:
        activate_url = f"{frontend_base}/activate?token={token}"
    else:
        # fallback: activate directly hitting API
        activate_url = "http://31.97.230.171:8000/api/faculty/activate?token=" + token

    # ✅ IMPORTANT FIX: do not crash if email not configured
    email_sent = False
    try:
        await send_activation_email(
            to_email=faculty.email,
            to_name=faculty.full_name,
            activate_url=activate_url,
        )
        email_sent = True
    except Exception as e:
        # don't fail the API if email isn't configured
        print(f"[WARN] Activation email not sent for {faculty.email}: {e}")

    return faculty, email_sent


async def activate_faculty(token: str, db: AsyncSession) -> None:
    # validate token signature + age
    max_age_seconds = int(os.getenv("ACTIVATION_TOKEN_EXPIRE_HOURS", "48")) * 3600
    try:
        data = verify_token(token, max_age_seconds=max_age_seconds)
        email = data.get("email")
        if not email:
            raise ValueError("Invalid token payload")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid or expired activation token")

    q = await db.execute(select(Faculty).where(Faculty.email == email))
    faculty = q.scalar_one_or_none()
    if not faculty:
        raise HTTPException(status_code=404, detail="Faculty not found")

    if faculty.is_active:
        return

    # verify stored hash matches
    if not faculty.activation_token_hash or faculty.activation_token_hash != hash_token(token):
        raise HTTPException(status_code=400, detail="Invalid activation token")

    if faculty.activation_expires_at and faculty.activation_expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Activation link expired")

    faculty.is_active = True
    faculty.activation_token_hash = None
    faculty.activation_expires_at = None

    await db.commit()