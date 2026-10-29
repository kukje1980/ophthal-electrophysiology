"""HTML pages (server-rendered shells; data is fetched via the JSON API)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import exam as exam_crud
from app.crud import patient as patient_crud
from app.crud import visit as visit_crud
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
def reception_page(request: Request, user=Depends(current_user)):
    """검사 접수 — the start screen: find or register the patient, record
    this visit's details, then start the exam."""
    return templates.TemplateResponse("reception.html", _ctx(request, user))


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db),
              user=Depends(current_user)):
    recent = exam_crud.list_recent(db, limit=15)
    # COUNT queries — never load every patient just to count them
    return templates.TemplateResponse("dashboard.html", _ctx(
        request, user, recent=recent, patient_count=patient_crud.count(db),
        exam_count=exam_crud.count(db),
        unsigned=exam_crud.list_unsigned(db, limit=30),
    ))


@router.get("/favicon.ico", include_in_schema=False)
def favicon():
    """No icon shipped yet; answer 204 so browsers stop logging a 404."""
    return Response(status_code=204)


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
def exam_new(patient_id: int, request: Request, visit_id: Optional[int] = None,
             db: Session = Depends(get_db), user=Depends(current_user)):
    p = patient_crud.get(db, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    visit = visit_crud.get(db, visit_id) if visit_id else None
    if visit is not None and visit.patient_id != p.id:
        visit = None
    return templates.TemplateResponse("exam.html", _ctx(
        request, user, patient=p, test_types=TEST_TYPES, visit=visit,
        visit_tests=[t for t in (visit.tests or "").split(",") if t] if visit else [],
    ))


@router.get("/reports/{exam_id}", response_class=HTMLResponse)
@router.get("/exams/{exam_id}", response_class=HTMLResponse)
def report_view(exam_id: int, request: Request,
                db: Session = Depends(get_db), user=Depends(current_user)):
    e = exam_crud.get(db, exam_id)
    if not e:
        raise HTTPException(404, "Exam not found")
    return templates.TemplateResponse("report.html", _ctx(
        request, user, exam_id=exam_id, patient_id=e.patient_id, embed=False,
    ))


@router.get("/live", response_class=HTMLResponse)
def live_page(request: Request, user=Depends(current_user)):
    """Live streaming oscilloscope (real-time amplifier link)."""
    return templates.TemplateResponse("live.html", _ctx(request, user))


@router.get("/reference", response_class=HTMLResponse)
def reference_page(request: Request, user=Depends(current_user)):
    """Laboratory normative reference-range management."""
    if not has_permission(user, "manage_reference"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("reference.html", _ctx(request, user))


@router.get("/account", response_class=HTMLResponse)
def account_page(request: Request, user=Depends(current_user)):
    return templates.TemplateResponse("account.html", _ctx(request, user))


@router.get("/admin", response_class=HTMLResponse)
def admin_page(request: Request, user=Depends(current_user)):
    if not has_permission(user, "manage_users"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse("admin.html", _ctx(
        request, user, roles=list(ROLE_LABELS.items()),
    ))
