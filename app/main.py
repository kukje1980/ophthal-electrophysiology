"""FastAPI application entry point."""
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import SessionLocal, init_db
from app.routers import (
    audit, auth, devices, exams, pages, patients, protocols, users,
)

# Paths reachable without a login session.
_PUBLIC = ("/login", "/logout", "/static", "/docs", "/openapi.json",
           "/redoc", "/favicon.ico")


def _seed_admin():
    """Create the initial admin account when the user table is empty."""
    from app.crud import user as user_crud
    from app.schemas.user import UserCreate

    db = SessionLocal()
    try:
        if user_crud.count(db) == 0:
            user_crud.create(db, UserCreate(
                username=settings.ADMIN_USERNAME,
                password=settings.ADMIN_PASSWORD,
                full_name="System Administrator",
                role="admin",
            ))
            print(f"[seed] created admin user '{settings.ADMIN_USERNAME}' "
                  f"— change the password after first login.")
    finally:
        db.close()


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_TITLE, version="0.1.0")

    @app.on_event("startup")
    def _startup():
        init_db()
        _seed_admin()

    @app.middleware("http")
    async def _auth_gate(request: Request, call_next):
        path = request.url.path
        if any(path == p or path.startswith(p) for p in _PUBLIC):
            return await call_next(request)
        if not request.session.get("user_id"):
            if path.startswith("/api"):
                return JSONResponse({"detail": "Authentication required"},
                                    status_code=401)
            return RedirectResponse(f"/login?next={quote(path)}", status_code=303)
        return await call_next(request)

    # SessionMiddleware is added last so it wraps (runs before) the auth gate,
    # making request.session available to it.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        session_cookie=settings.SESSION_COOKIE,
        https_only=settings.SESSION_HTTPS_ONLY,
        same_site="lax",
    )

    app.mount("/static", StaticFiles(directory="static"), name="static")

    # JSON API
    app.include_router(patients.router)
    app.include_router(exams.router)
    app.include_router(protocols.router)
    app.include_router(devices.router)
    app.include_router(users.router)
    app.include_router(audit.router)
    # Auth + HTML pages
    app.include_router(auth.router)
    app.include_router(pages.router)

    return app


app = create_app()
