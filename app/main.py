from dotenv import load_dotenv
import os

# Load .env properly (works from uvicorn or systemd)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routes.auth import router as auth_router
from app.routes.faculty import router as faculty_router
from app.routes.students import router as students_router   # ✅ NEW


app = FastAPI(
    title="Vikasana Foundation API",
    description="Backend API for the Vikasana Admin Panel",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
)

# ───────────────── CORS FIX ─────────────────
# fallback if env variable missing
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
app.include_router(students_router, prefix="/api")   # ✅ NEW

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