"""FastAPI routers."""
from app.routers import (
    account, audit, auth, devices, exams, pages, patients, protocols, users,
)

__all__ = [
    "account", "audit", "auth", "devices", "exams", "pages",
    "patients", "protocols", "users",
]
