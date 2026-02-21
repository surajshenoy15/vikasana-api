from app.core.database import Base  # ✅ export Base from here if you want
from .student import Student
from app.models.admin import Admin  # existing
from app.models.faculty import Faculty  # <-- if typo, correct
