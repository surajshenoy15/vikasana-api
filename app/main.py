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

# ✅ EVENTS router (admin + student events)
from app.routes.events import router as events_router

# activity routers (student + admin)
from app.routes.activity import router as student_activity_router
from app.routes.activity import admin_router as admin_activity_router
from app.routes.activity import legacy_router as student_legacy_router

# students routers
from app.routes.students import (
    faculty_router as faculty_students_router,
    admin_router as admin_students_router,
    student_router as student_profile_router,
)

# face router
from app.routes.face_routes import router as face_router

# ✅ admin sessions router
from app.routes.admin_sessions import router as admin_sessions_router

# ✅ activity types router (NEW)
from app.routes.activity_types import router as activity_types_router

# ✅ certificates routers (NEW)
from app.routes.public_certificates import router as public_certificates_router
from app.routes.student_certificates import router as student_certificates_router


app = FastAPI(
    title="Vikasana Foundation API",
    description="Backend API for the Vikasana Admin Panel",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)


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


# ───────────────── CORS ─────────────────
origins = settings.origins_list or [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://31.97.230.171:3000",
    "http://31.97.230.171:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# ✅ Admin Sessions
app.include_router(admin_sessions_router, prefix="/api")  # -> /api/admin/sessions

# ✅ Activity Types (NEW)
# Public:  GET  /api/activity-types
# Admin:   POST /api/activity-types
#         PATCH/GET/DELETE /api/activity-types/{id}
app.include_router(activity_types_router, prefix="/api")

# ✅ Events (admin + student)
# includes: /api/admin/events/{id}/end  and /api/student/events etc
app.include_router(events_router, prefix="/api")

# ✅ Certificates (NEW)
# Public verify:   GET /api/public/certificates/verify?cert_id=&sig=
# Student link:    GET /api/student/certificates/{session_id}/download-url
app.include_router(public_certificates_router, prefix="/api")
app.include_router(student_certificates_router, prefix="/api")

# Other
app.include_router(activity_summary_router, prefix="/api")
app.include_router(face_router, prefix="/api")  # -> /api/face/...

# ───────────────── HEALTH ─────────────────
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "app": "Vikasana Foundation API", "env": settings.APP_ENV}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}