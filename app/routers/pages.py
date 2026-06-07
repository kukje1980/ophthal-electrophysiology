"""HTML pages (server-rendered shells; data is fetched via the JSON API)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.crud import exam as exam_crud
from app.crud import patient as patient_crud
from app.database import get_db
from app.iscev import TEST_TYPES

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    recent = exam_crud.list_recent(db, limit=15)
    patients = patient_crud.list_all(db)
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "recent": recent,
        "patient_count": len(patients),
        "exam_count": len(recent),
    })


@router.get("/patients", response_class=HTMLResponse)
def patients_page(request: Request):
    return templates.TemplateResponse("patients.html", {"request": request})


@router.get("/patients/{patient_id}", response_class=HTMLResponse)
def patient_detail(patient_id: int, request: Request,
                   db: Session = Depends(get_db)):
    p = patient_crud.get(db, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return templates.TemplateResponse("patient_detail.html", {
        "request": request,
        "patient": p,
        "test_types": TEST_TYPES,
    })


@router.get("/stimulus", response_class=HTMLResponse)
def stimulus_monitor(request: Request):
    """Patient-facing monitor stimulator surface (pattern / flash / flicker)."""
    return templates.TemplateResponse("stimulus.html", {"request": request})


@router.get("/exam/new", response_class=HTMLResponse)
def exam_new(patient_id: int, request: Request,
             db: Session = Depends(get_db)):
    p = patient_crud.get(db, patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    return templates.TemplateResponse("exam.html", {
        "request": request,
        "patient": p,
        "test_types": TEST_TYPES,
    })


@router.get("/exams/{exam_id}", response_class=HTMLResponse)
def exam_view(exam_id: int, request: Request, db: Session = Depends(get_db)):
    e = exam_crud.get(db, exam_id)
    if not e:
        raise HTTPException(404, "Exam not found")
    return templates.TemplateResponse("report.html", {
        "request": request,
        "exam_id": exam_id,
        "embed": False,
    })


@router.get("/reports/{exam_id}", response_class=HTMLResponse)
def report_view(exam_id: int, request: Request, db: Session = Depends(get_db)):
    e = exam_crud.get(db, exam_id)
    if not e:
        raise HTTPException(404, "Exam not found")
    return templates.TemplateResponse("report.html", {
        "request": request,
        "exam_id": exam_id,
        "embed": False,
    })
