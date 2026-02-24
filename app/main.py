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
from app.routes.auth import router as auth_router
from app.routes.faculty import router as faculty_router
from app.routes.students import router as students_router
from app.routes.student_auth import router as student_auth_router
from app.routes.activity_summary import router as activity_summary_router
from app.routes.events import router as events_router
from app.routes.activity import router as student_activity_router
from app.routes.activity import admin_router as admin_activity_router


app = FastAPI(
    title="Vikasana Foundation API",
    description="Backend API for the Vikasana Admin Panel",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ───────── SAFE VALIDATION HANDLER (FIXES UNICODE CRASH) ─────────

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
app.include_router(faculty_router, prefix="/api")
app.include_router(students_router, prefix="/api")
app.include_router(student_auth_router, prefix="/api")

app.include_router(student_activity_router, prefix="/api")
app.include_router(admin_activity_router, prefix="/api")
app.include_router(activity_summary_router, prefix="/api")
app.include_router(events_router, prefix="/api")

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