"""FastAPI routers."""
from app.routers import (
    account, audit, auth, devices, exams, live, pages, patients, protocols,
    reference, system, users,
)

__all__ = [
    "account", "audit", "auth", "devices", "exams", "live", "pages",
    "patients", "protocols", "reference", "system", "users",
]
