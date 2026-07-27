"""Authentication routes: login page, login/logout, session handling."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import user as user_crud
from app.database import get_db
from app.security import decrypt_phi, totp, verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str = ""):
    if request.session.get("user_id"):
        return RedirectResponse(next or "/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request, "next": next, "error": error,
    })


def _login_error(request, next, message, *, need_otp=False, status=401):
    return templates.TemplateResponse("login.html", {
        "request": request, "next": next, "error": message, "need_otp": need_otp,
    }, status_code=status)


@router.post("/login")
def login(request: Request, username: str = Form(...),
          password: str = Form(...), otp: str = Form(""),
          next: str = Form("/"), db: Session = Depends(get_db)):
    user = user_crud.get_by_username(db, username)

    # Account lockout takes precedence.
    if user and user_crud.is_locked(user):
        user_crud.audit(db, user=user, action="login_locked", request=request)
        return _login_error(request, next,
                            "계정이 잠겼습니다. 잠시 후 다시 시도하세요.")

    if not user or not user.is_active or not verify_password(
        password, user.password_hash
    ):
        locked = user_crud.record_failed_login(db, user) if user else False
        user_crud.audit(db, user=user,
                        action="login_locked" if locked else "login_failed",
                        detail=f"username={username}", request=request)
        msg = ("연속 실패로 계정이 잠겼습니다. 15분 후 다시 시도하세요."
               if locked else "아이디 또는 비밀번호가 올바르지 않습니다.")
        return _login_error(request, next, msg)

    # Second factor, when enabled.
    if user.totp_enabled:
        if not otp:
            return _login_error(request, next, "인증 앱의 6자리 코드를 입력하세요.",
                                need_otp=True)
        if not totp.verify(decrypt_phi(user.totp_secret), otp):
            user_crud.record_failed_login(db, user)
            user_crud.audit(db, user=user, action="login_2fa_failed",
                            request=request)
            return _login_error(request, next, "인증 코드가 올바르지 않습니다.",
                                need_otp=True)

    user_crud.reset_failed_login(db, user)
    request.session["user_id"] = user.id
    user.last_login = datetime.utcnow()
    db.commit()
    user_crud.audit(db, user=user, action="login", request=request)
    return RedirectResponse(next or "/", status_code=303)


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db)):
    uid = request.session.get("user_id")
    if uid:
        user = user_crud.get(db, uid)
        user_crud.audit(db, user=user, action="logout", request=request)
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
