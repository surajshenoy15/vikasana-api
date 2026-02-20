from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.controllers.auth_controller import get_me, login
from app.core.database import get_db
from app.core.dependencies import get_current_admin
from app.models.admin import Admin
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse

router = APIRouter(prefix="/auth", tags=["Admin Auth"])


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Admin Login",
    description="""
Authenticate with email + password.
Returns a JWT Bearer token to use in all other requests.

**How to use the token:**
Add to request headers: `Authorization: Bearer <your_token>`
    """,
)
async def admin_login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    return await login(payload, db)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get Current Admin",
    description="Returns the authenticated admin's profile. Requires Bearer token in header.",
)
async def me(
    current_admin: Admin = Depends(get_current_admin),
) -> MeResponse:
    return await get_me(current_admin)


@router.post(
    "/logout",
    summary="Logout",
    description="""
JWT tokens are stateless — the server has no session to destroy.
To logout: delete the token from your frontend (sessionStorage/localStorage).
This endpoint exists to give the frontend a clean API to call.
    """,
)
async def logout() -> dict:
    return {"detail": "Logged out. Delete your token on the client side."}
