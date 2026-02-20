from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes.auth import router as auth_router
from app.routes.faculty import router as faculty_router  # ✅ NEW

app = FastAPI(
    title="Vikasana Foundation API",
    description="Backend API for the Vikasana Admin Panel",
    version="1.0.0",
    # Disable docs in production by setting APP_ENV=production in .env
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ── CORS ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes ────────────────────────────────────────────────────────────
# All endpoints will be under /api
#   /api/auth/...
#   /api/faculty/...
app.include_router(auth_router, prefix="/api")
app.include_router(faculty_router, prefix="/api")  # ✅ NEW

# ── Health endpoints ──────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "ok",
        "app": "Vikasana Foundation API",
        "env": settings.APP_ENV,
    }


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}