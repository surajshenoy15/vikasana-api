# app/main.py

from dotenv import load_dotenv
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.status import HTTP_422_UNPROCESSABLE_ENTITY

from app.core.config import settings

# ───────────────── ROUTER IMPORTS ─────────────────
from app.routes.auth import router as auth_router
from app.routes.faculty import router as faculty_main_router
from app.routes.student_auth import router as student_auth_router
from app.routes.activity_summary import router as activity_summary_router
from app.routes.events import router as events_router
from app.routes.activity import (
    router as student_activity_router,
    admin_router as admin_activity_router,
    legacy_router as student_legacy_router,
)
from app.routes.students import (
    faculty_router as faculty_students_router,
    admin_router as admin_students_router,
    student_router as student_profile_router,
)
from app.routes.face_routes import router as face_router
from app.routes.admin_sessions import router as admin_sessions_router
from app.routes.activity_types import router as activity_types_router
from app.routes.public_verify import router as public_verify_router
from app.routes.student_certificates import router as student_certificates_router

# ✅ NEW: Admin Dashboard routes (for backend-powered dashboard)
from app.routes.admin_dashboard import router as admin_dashboard_router


# ───────────────── APP INIT ─────────────────
app = FastAPI(
    title="Vikasana Foundation API",
    description="Backend API for the Vikasana Admin Panel",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


# ───────────────── SANITIZER ─────────────────
def _sanitize(obj):
    if isinstance(obj, (bytes, bytearray)):
        return f"<bytes:{len(obj)}>"
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    return obj


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    safe_errors = _sanitize(exc.errors())
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": safe_errors},
    )


# ───────────────── CORS CONFIG ─────────────────

default_origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "http://31.97.230.171",
    "http://31.97.230.171:3000",
    "http://31.97.230.171:5173",
    "https://31.97.230.171",
    "https://31.97.230.171:3000",
    "https://31.97.230.171:5173",
]

origins = set(default_origins)
if settings.origins_list:
    origins.update([o.strip() for o in settings.origins_list if o and o.strip()])

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ───────────────── DEBUG ORIGIN LOGGER (TEMPORARY) ─────────────────
@app.middleware("http")
async def log_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if origin:
        print(f"🌍 ORIGIN: {origin} | PATH: {request.url.path}")
    response = await call_next(request)
    return response


# ───────────────── ROUTES ─────────────────
app.include_router(auth_router, prefix="/api")
app.include_router(faculty_main_router, prefix="/api")

app.include_router(faculty_students_router, prefix="/api")
app.include_router(admin_students_router, prefix="/api")
app.include_router(student_profile_router, prefix="/api")

app.include_router(student_auth_router, prefix="/api")

app.include_router(student_activity_router, prefix="/api")
app.include_router(student_legacy_router, prefix="/api")
app.include_router(admin_activity_router, prefix="/api")

app.include_router(admin_sessions_router, prefix="/api")
app.include_router(activity_types_router, prefix="/api")
app.include_router(events_router, prefix="/api")

app.include_router(public_verify_router, prefix="/api")
app.include_router(student_certificates_router, prefix="/api")

app.include_router(activity_summary_router, prefix="/api")
app.include_router(face_router, prefix="/api")

# ✅ NEW: dashboard endpoints:
# /api/admin/dashboard/stats
# /api/admin/dashboard/category-progress
# /api/admin/dashboard/student-progress
# /api/admin/dashboard/recent-submissions
app.include_router(admin_dashboard_router, prefix="/api")


# ───────────────── HEALTH ─────────────────
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