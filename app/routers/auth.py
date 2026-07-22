"""Authentication routes: login page, login/logout, session handling."""
from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import user as user_crud
from app.database import get_db
from app.security import verify_password

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory="templates")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str = ""):
    if request.session.get("user_id"):
        return RedirectResponse(next or "/", status_code=303)
    return templates.TemplateResponse("login.html", {
        "request": request, "next": next, "error": error,
    })


@router.post("/login")
def login(request: Request, username: str = Form(...),
          password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    user = user_crud.get_by_username(db, username)
    if not user or not user.is_active or not verify_password(
        password, user.password_hash
    ):
        user_crud.audit(db, user=user, action="login_failed",
                        detail=f"username={username}", request=request)
        return templates.TemplateResponse("login.html", {
            "request": request, "next": next,
            "error": "아이디 또는 비밀번호가 올바르지 않습니다.",
        }, status_code=401)

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
