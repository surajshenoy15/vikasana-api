from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.student import Student
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.admin import Admin
from app.models.faculty import Faculty  # ✅ NEW

bearer = HTTPBearer(auto_error=False)


def _not_authenticated_exception() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    not_authenticated = _not_authenticated_exception()

    if not credentials:
        raise not_authenticated

    try:
        payload = decode_access_token(credentials.credentials)
        admin_id = int(payload["sub"])
        if payload.get("type") != "access":
            raise not_authenticated
    except (JWTError, KeyError, ValueError):
        raise not_authenticated

    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin = result.scalar_one_or_none()

    if admin is None:
        raise not_authenticated

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This admin account has been deactivated",
        )

    return admin


async def get_current_faculty(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Faculty:
    """
    Faculty auth guard dependency.

    Usage:
        @router.post("/faculty/students")
        async def add_students(
            faculty: Faculty = Depends(get_current_faculty),
            db: AsyncSession = Depends(get_db),
        ):
            ...

    What it does:
    1. Reads Bearer token
    2. Verifies JWT + expiry
    3. Loads faculty from DB
    4. Checks faculty is active (if field exists)
    """
    not_authenticated = _not_authenticated_exception()

    if not credentials:
        raise not_authenticated

    try:
        payload = decode_access_token(credentials.credentials)
        faculty_id = int(payload["sub"])

        # ✅ ensure it is an access token (same as admin)
        if payload.get("type") != "access":
            raise not_authenticated

        # ✅ OPTIONAL: if you encode role in token, enforce it
        # (won't break if role is absent)
        role = payload.get("role")
        if role and role != "faculty":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized as faculty",
            )

    except (JWTError, KeyError, ValueError):
        raise not_authenticated

    result = await db.execute(select(Faculty).where(Faculty.id == faculty_id))
    faculty = result.scalar_one_or_none()

    if faculty is None:
        raise not_authenticated

    # ✅ Only check is_active if your Faculty model has it
    if hasattr(faculty, "is_active") and not faculty.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This faculty account has been deactivated",
        )

    return faculty

async def get_current_student(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Student:
    """
    Student auth guard dependency.

    Expects:
      - Bearer token
      - decode_access_token() returns payload with:
          payload["sub"] = student_id
          payload["type"] == "access"
      - Optional: payload["role"] == "student" (if you set it)

    Usage:
        student=Depends(get_current_student)
    """
    not_authenticated = _not_authenticated_exception()

    if not credentials:
        raise not_authenticated

    try:
        payload = decode_access_token(credentials.credentials)
        student_id = int(payload["sub"])

        if payload.get("type") != "access":
            raise not_authenticated

        # Optional role enforcement
        role = payload.get("role")
        if role and role != "student":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized as student",
            )

    except (JWTError, KeyError, ValueError):
        raise not_authenticated

    result = await db.execute(select(Student).where(Student.id == student_id))
    student = result.scalar_one_or_none()

    if student is None:
        raise not_authenticated

    # Optional is_active check (only if exists in model)
    if hasattr(student, "is_active") and not student.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This student account has been deactivated",
        )

    return student