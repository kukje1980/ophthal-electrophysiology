"""HTML pages (server-rendered shells; data is fetched via the JSON API)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import exam as exam_crud
from app.crud import patient as patient_crud
from app.database import get_db
from app.iscev import TEST_TYPES
from app.security import ROLES, current_user, has_permission
from app.security.auth import ROLE_LABELS

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


def _ctx(request: Request, user, **extra) -> dict:
    """Common template context: request, the current user and its permissions."""
    perms = sorted(ROLES.get(user.role, set())) if user else []
    ctx = {
        "request": request,
        "user": user,
        "perms": perms,
        "role_label": ROLE_LABELS.get(user.role, user.role) if user else "",
    }
    ctx.update(extra)
    return ctx


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db),
              user=Depends(current_user)):
    recent = exam_crud.list_recent(db, limit=15)
    patients = patient_crud.list_all(db)
    return templates.TemplateResponse("dashboard.html", _ctx(
        request, user, recent=recent, patient_count=len(patients),
        exam_count=len(recent),
    ))


@router.get("/patients", response_class=HTMLResponse)
def patients_page(request: Request, user=Depends(current_user)):
    return templates.TemplateResponse("patients.html", _ctx(request, user))


@router.get("/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(patient_id: int, request: Request,
                   db: Session = Depends(get_db), user=Depends(current_user)):
    p = patient_crud.get(db, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return templates.TemplateResponse("patient_detail.html", _ctx(
        request, user, patient=p, test_types=TEST_TYPES,
    ))


@router.get("/stimulus", response_class=HTMLResponse)
def stimulus_monitor(request: Request, user=Depends(current_user)):
    """Patient-facing monitor stimulator surface (pattern / flash / flicker)."""
    return templates.TemplateResponse("stimulus.html", _ctx(request, user))


@router.get("/exam/new", response_class=HTMLResponse)
def exam_new(patient_id: int, request: Request,
             db: Session = Depends(get_db), user=Depends(current_user)):
    p = patient_crud.get(db, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return templates.TemplateResponse("exam.html", _ctx(
        request, user, patient=p, test_types=TEST_TYPES,
    ))


@router.get("/reports/{exam_id}", response_class=HTMLResponse)
@router.get("/exams/{exam_id}", response_class=HTMLResponse)
def report_view(exam_id: int, request: Request,
                db: Session = Depends(get_db), user=Depends(current_user)):
    e = exam_crud.get(db, exam_id)
    if not e:
        raise HTTPException(404, "Exam not found")
    return templates.TemplateResponse("report.html", _ctx(
        request, user, exam_id=exam_id, embed=False,
    ))


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, user=Depends(current_user)):
    if not has_permission(user, "manage_users"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("admin.html", _ctx(
        request, user, roles=list(ROLE_LABELS.items()),
    ))
