from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.admin import Admin

bearer = HTTPBearer(auto_error=False)


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> Admin:
    """
    Reusable auth guard dependency.

    Usage in any protected route:
        @router.get("/something")
        async def protected_route(admin: Admin = Depends(get_current_admin)):
            return {"hello": admin.name}

    What it does:
    1. Reads the Bearer token from Authorization header
    2. Verifies JWT signature and expiry
    3. Loads admin from DB
    4. Checks admin is still active
    5. Returns admin object — or raises 401/403
    """
    not_authenticated = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing token",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not credentials:
        raise not_authenticated

    try:
        payload  = decode_access_token(credentials.credentials)
        admin_id = int(payload["sub"])
        if payload.get("type") != "access":
            raise not_authenticated
    except (JWTError, KeyError, ValueError):
        raise not_authenticated

    result = await db.execute(select(Admin).where(Admin.id == admin_id))
    admin  = result.scalar_one_or_none()

    if admin is None:
        raise not_authenticated

    if not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This admin account has been deactivated",
        )

    return admin
