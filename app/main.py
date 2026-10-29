"""FastAPI application entry point."""
import logging
import uuid
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import OperationalError
from starlette.middleware.sessions import SessionMiddleware

from app import backup
from app.config import settings
from app.database import SessionLocal, checkpoint, engine, init_db
from app.logging_setup import setup_logging
from app.routers import (
    account, audit, auth, devices, exams, live, pages, patients, protocols,
    reference, system, users, visits,
)

log = logging.getLogger("app")

# Paths reachable without a login session.
_PUBLIC = ("/login", "/logout", "/static", "/docs", "/openapi.json",
           "/redoc", "/favicon.ico", "/health")


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


def _seed_reference():
    """Load the demonstration reference ranges when the lab has none yet."""
    from app.crud import reference as reference_crud

    db = SessionLocal()
    try:
        if reference_crud.count(db) == 0:
            n = reference_crud.seed_demo(db)
            print(f"[seed] loaded {n} demonstration reference ranges "
                  f"— replace with laboratory norms at /reference.")
    finally:
        db.close()


def _check_phi_key():
    """Shout if encrypted records no longer decrypt (the key was changed)."""
    from app.security.crypto import phi_key_problems

    db = SessionLocal()
    try:
        bad = phi_key_problems(db)
    finally:
        db.close()
    if bad:
        log.critical("%d encrypted national id(s) cannot be decrypted — "
                     "SECRET_KEY / PHI_ENCRYPTION_KEY changed? Restore the "
                     "previous key; do not edit those records.", bad)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    setup_logging()
    init_db()
    _seed_admin()
    _seed_reference()
    _check_phi_key()
    scheduler = None
    if settings.BACKUP_ENABLED and backup.supported():
        scheduler = backup.BackupScheduler()
        scheduler.start()
    elif not backup.supported():
        log.warning("built-in backups cover SQLite only — configure the "
                    "database's own backup tooling")
    log.info("server started (db=%s)", engine.url.render_as_string(hide_password=True))
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.stop()
        try:
            checkpoint()
        except Exception:  # noqa: BLE001
            log.exception("WAL checkpoint on shutdown failed")
        engine.dispose()
        log.info("server stopped")


def create_app() -> FastAPI:
    app = FastAPI(title=settings.APP_TITLE, version="0.1.0", lifespan=_lifespan)

    @app.exception_handler(RequestValidationError)
    async def _invalid(request: Request, exc: RequestValidationError):
        # Same shape as FastAPI's default minus the echoed "input": echoing a
        # 200k-sample array (or a NaN, which is not valid JSON) back is wasteful
        # at best and a 500 at worst.
        errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
        return JSONResponse({"detail": jsonable_encoder(errors)}, status_code=422)

    @app.exception_handler(OperationalError)
    async def _db_busy(request: Request, exc: OperationalError):
        # e.g. "database is locked" under heavy concurrent writes: the
        # transaction was rolled back, so the client may simply retry.
        log.warning("database operational error on %s %s: %s",
                    request.method, request.url.path, exc.orig)
        return JSONResponse(
            {"detail": "데이터베이스가 일시적으로 응답하지 않습니다. 잠시 후 자동으로 다시 시도합니다."},
            status_code=503, headers={"Retry-After": "2"})

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        error_id = uuid.uuid4().hex[:8]
        log.exception("unhandled error %s on %s %s", error_id,
                      request.method, request.url.path)
        message = f"서버 내부 오류가 발생했습니다 (오류 ID {error_id}). 관리자에게 문의하세요."
        if request.url.path.startswith("/api"):
            return JSONResponse({"detail": message, "error_id": error_id},
                                status_code=500)
        return HTMLResponse(f"<h1>500</h1><p>{message}</p><p><a href='/'>홈으로</a></p>",
                            status_code=500)

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

    # SessionMiddleware is added after the auth gate so it wraps (runs before)
    # it, making request.session available to it.
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        session_cookie=settings.SESSION_COOKIE,
        https_only=settings.SESSION_HTTPS_ONLY,
        same_site="lax",
    )
    # Waveform JSON compresses ~5-10x: much faster reports over slow links.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.mount("/static", StaticFiles(directory="static"), name="static")

    # JSON API
    app.include_router(patients.router)
    app.include_router(exams.router)
    app.include_router(protocols.router)
    app.include_router(devices.router)
    app.include_router(users.router)
    app.include_router(audit.router)
    app.include_router(account.router)
    app.include_router(live.router)  # WebSocket live stream
    app.include_router(reference.router)
    app.include_router(system.router)  # health, backups, trash
    app.include_router(visits.router)
    # Auth + HTML pages
    app.include_router(auth.router)
    app.include_router(pages.router)

    return app


app = create_app()
