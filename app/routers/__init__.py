"""FastAPI routers."""
from app.routers import (
    audit, auth, devices, exams, pages, patients, protocols, users,
)

__all__ = [
    "audit", "auth", "devices", "exams", "pages",
    "patients", "protocols", "users",
]
