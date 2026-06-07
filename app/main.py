"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import devices, exams, pages, patients, protocols


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_TITLE, version="0.1.0")

    @app.on_event("startup")
    def _startup():
        init_db()

    app.mount("/static", StaticFiles(directory="static"), name="static")

    # JSON API
    app.include_router(patients.router)
    app.include_router(exams.router)
    app.include_router(protocols.router)
    app.include_router(devices.router)
    # HTML pages
    app.include_router(pages.router)

    return app


app = create_app()
