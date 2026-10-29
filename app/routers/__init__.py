"""FastAPI routers."""
from app.routers import (
    account, audit, auth, devices, exams, live, pages, patients, photos,
    protocols, reference, users,
)

__all__ = [
    "account", "audit", "auth", "devices", "exams", "live", "pages",
    "patients", "photos", "protocols", "reference", "users",
]
