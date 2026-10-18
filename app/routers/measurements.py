"""Cursor (marker) editing API — move, add, remove, re-detect.

Every edit re-measures the affected waveform with the same rules as the
automatic detector, so manual and automatic markers stay comparable. Signed
reports are read-only (409)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.crud import exam as crud
from app.crud import user as audit_crud
from app.crud.exam import ExamLocked
from app.database import get_db
from app.iscev import known_markers
from app.schemas import MeasurementAdd, MeasurementMove, MeasurementOut, WaveformOut
from app.security import require_permission

router = APIRouter(prefix="/api", tags=["measurements"])


@router.get("/markers")
def list_known_markers(_=Depends(require_permission("view_report"))):
    """Marker names the analysis layer knows how to measure."""
    return {"markers": known_markers()}


@router.put("/measurements/{measurement_id}", response_model=MeasurementOut)
def move_measurement(measurement_id: int, data: MeasurementMove,
                     request: Request, db: Session = Depends(get_db),
                     user=Depends(require_permission("edit_markers"))):
    try:
        m = crud.move_marker(db, measurement_id, data.latency_ms)
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    if m is None:
        raise HTTPException(404, "Measurement not found")
    audit_crud.audit(db, user=user, action="marker.move", entity="exam",
                     entity_id=m.waveform.exam_id,
                     detail=f"{m.waveform.step} {m.waveform.eye} {m.marker} -> {m.latency_ms} ms",
                     request=request)
    return m


@router.post("/waveforms/{waveform_id}/measurements",
             response_model=MeasurementOut, status_code=201)
def add_measurement(waveform_id: int, data: MeasurementAdd, request: Request,
                    db: Session = Depends(get_db),
                    user=Depends(require_permission("edit_markers"))):
    try:
        m = crud.add_marker(db, waveform_id, data.marker, data.latency_ms)
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    except KeyError as e:
        raise HTTPException(400, str(e))
    if m is None:
        raise HTTPException(404, "Waveform not found")
    audit_crud.audit(db, user=user, action="marker.add", entity="exam",
                     entity_id=m.waveform.exam_id,
                     detail=f"{m.waveform.step} {m.waveform.eye} {m.marker} @ {m.latency_ms} ms",
                     request=request)
    return m


@router.delete("/measurements/{measurement_id}", status_code=204)
def delete_measurement(measurement_id: int, request: Request,
                       db: Session = Depends(get_db),
                       user=Depends(require_permission("edit_markers"))):
    m = db.get(crud.Measurement, measurement_id)
    if m is None:
        raise HTTPException(404, "Measurement not found")
    exam_id, label = m.waveform.exam_id, f"{m.waveform.step} {m.waveform.eye} {m.marker}"
    try:
        crud.remove_marker(db, measurement_id)
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    audit_crud.audit(db, user=user, action="marker.delete", entity="exam",
                     entity_id=exam_id, detail=label, request=request)


@router.post("/waveforms/{waveform_id}/redetect", response_model=WaveformOut)
def redetect_waveform(waveform_id: int, request: Request,
                      db: Session = Depends(get_db),
                      user=Depends(require_permission("edit_markers"))):
    try:
        wf = crud.redetect(db, waveform_id)
    except ExamLocked as e:
        raise HTTPException(409, str(e))
    if wf is None:
        raise HTTPException(404, "Waveform not found")
    audit_crud.audit(db, user=user, action="marker.redetect", entity="exam",
                     entity_id=wf.exam_id, detail=f"{wf.step} {wf.eye}",
                     request=request)
    return wf
