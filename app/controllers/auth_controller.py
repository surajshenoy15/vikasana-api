from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.admin import Admin
from app.schemas.auth import AdminInfo, LoginRequest, LoginResponse, MeResponse


async def login(payload: LoginRequest, db: AsyncSession) -> LoginResponse:
    """
    Admin login — all business logic lives here, not in the route.

    Security measures:
    ─────────────────
    1. Always runs verify_password even when admin not found
       → Prevents timing attacks that reveal whether an email exists

    2. Returns the same error for wrong email AND wrong password
       → Prevents email enumeration (attacker can't tell which is wrong)

    3. Checks is_active AFTER password check
       → Doesn't reveal whether account exists before auth succeeds

    4. Updates last_login_at on success
       → Audit trail in DB
    """

    # Step 1 — Find admin by email
    result = await db.execute(
        select(Admin).where(Admin.email == payload.email)
    )
    admin = result.scalar_one_or_none()

    # Step 2 — Always verify password (timing-safe)
    # If admin not found, verify against a dummy hash so timing is identical
    DUMMY_HASH = "$2b$12$dummyhashXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    password_ok = verify_password(
        payload.password,
        admin.password_hash if admin else DUMMY_HASH,
    )

    # Step 3 — Single generic error for not found OR wrong password
    if not admin or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    # Step 4 — Check account is active
    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is deactivated. Contact support.",
        )

    # Step 5 — Record login timestamp
    admin.last_login_at = datetime.now(timezone.utc)
    db.add(admin)
    await db.flush()

    # Step 6 — Issue JWT
    token = create_access_token(admin.id, admin.email)

    return LoginResponse(
        access_token=token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        admin=AdminInfo(
            id=admin.id,
            name=admin.name,
            email=admin.email,
        ),
    )


async def get_me(admin: Admin) -> MeResponse:
    """Returns current admin profile. No DB call needed — admin already loaded by dependency."""
    return MeResponse(
        id=admin.id,
        name=admin.name,
        email=admin.email,
        is_active=admin.is_active,
        last_login_at=admin.last_login_at,
        created_at=admin.created_at,
    )
