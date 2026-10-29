"""Pagination, soft delete / restore, idempotent writes, bounded fields."""
import time
import uuid

from app.database import SessionLocal
from app.models import Patient


def test_patient_list_is_paginated(client, make_patient):
    tag = uuid.uuid4().hex[:6]
    for i in range(7):
        make_patient(name=f"페이지{tag}-{i}")
    r = client.get(f"/api/patients?q=페이지{tag}&limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3
    assert r.headers["X-Total-Count"] == "7"
    r2 = client.get(f"/api/patients?q=페이지{tag}&limit=3&offset=6")
    assert len(r2.json()) == 1
    assert client.get("/api/patients?limit=100000").status_code == 422


def test_list_stays_fast_with_many_patients(client):
    db = SessionLocal()
    try:
        db.bulk_save_objects([Patient(mrn=f"BULK-{uuid.uuid4().hex}", name=f"대량{i}")
                              for i in range(5000)])
        db.commit()
    finally:
        db.close()
    t0 = time.perf_counter()
    r = client.get("/api/patients?limit=50")
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200 and len(r.json()) == 50
    assert int(r.headers["X-Total-Count"]) >= 5000
    assert elapsed < 2.0, f"patient list took {elapsed:.2f}s"
    # dashboard counts with COUNT(*) instead of loading every row
    assert client.get("/").status_code == 200


def test_soft_delete_and_restore(client, make_patient, protocol_key):
    p = make_patient()
    exam = client.post("/api/exams", json={"patient_id": p["id"], "protocol": protocol_key}).json()

    assert client.delete(f"/api/patients/{p['id']}").status_code == 204
    assert client.get(f"/api/patients/{p['id']}").status_code == 404
    assert client.get(f"/api/exams/{exam['id']}").status_code == 404  # hidden with patient
    trash = client.get("/api/trash").json()
    assert any(t["id"] == p["id"] for t in trash["patients"])
    # the MRN stays reserved while the record is in the trash
    r = client.post("/api/patients", json={"mrn": p["mrn"], "name": "dup"})
    assert r.status_code == 409 and "휴지통" in r.json()["detail"]

    assert client.post(f"/api/trash/patients/{p['id']}/restore").status_code == 200
    assert client.get(f"/api/patients/{p['id']}").status_code == 200
    assert client.get(f"/api/exams/{exam['id']}").status_code == 200

    assert client.delete(f"/api/exams/{exam['id']}").status_code == 204
    assert client.get(f"/api/exams?patient_id={p['id']}").json() == []
    assert client.post(f"/api/trash/exams/{exam['id']}/restore").status_code == 200
    assert len(client.get(f"/api/exams?patient_id={p['id']}").json()) == 1


def _record_body(pid, protocol_key, client, exam_id=None):
    proto = client.get(f"/api/protocols/{protocol_key}").json()
    return {"patient_id": pid, "protocol": protocol_key,
            "step_key": proto["steps"][0]["key"], "eye": "OD",
            "samples": [float(i % 50) for i in range(500)], "sampling_rate": 1000,
            "duration_ms": 500, "n_sweeps": 40, "exam_id": exam_id}


def test_retried_record_is_not_duplicated(client, make_patient, protocol_key):
    p = make_patient()
    body = _record_body(p["id"], protocol_key, client)
    key = {"Idempotency-Key": uuid.uuid4().hex}
    first = client.post("/api/exams/record", json=body, headers=key)
    assert first.status_code == 201
    again = client.post("/api/exams/record", json=body, headers=key)  # lost response → retry
    assert again.json()["id"] == first.json()["id"]
    assert len(again.json()["waveforms"]) == 1

    # appending to the exam: same key twice still adds exactly one trace
    body2 = _record_body(p["id"], protocol_key, client, exam_id=first.json()["id"])
    key2 = {"Idempotency-Key": uuid.uuid4().hex}
    client.post("/api/exams/record", json=body2, headers=key2)
    r = client.post("/api/exams/record", json=body2, headers=key2)
    assert len(r.json()["waveforms"]) == 2


def test_retried_create_returns_original(client, protocol_key):
    key = {"Idempotency-Key": uuid.uuid4().hex}
    body = {"mrn": f"IDEM-{uuid.uuid4().hex[:8]}", "name": "재시도"}
    a = client.post("/api/patients", json=body, headers=key)
    b = client.post("/api/patients", json=body, headers=key)
    assert a.status_code == 201 and b.status_code == 201
    assert a.json()["id"] == b.json()["id"]

    ekey = {"Idempotency-Key": uuid.uuid4().hex}
    e1 = client.post("/api/exams", json={"patient_id": a.json()["id"], "protocol": protocol_key}, headers=ekey)
    e2 = client.post("/api/exams", json={"patient_id": a.json()["id"], "protocol": protocol_key}, headers=ekey)
    assert e1.json()["id"] == e2.json()["id"]
    assert len(client.get(f"/api/exams?patient_id={a.json()['id']}").json()) == 1


def test_idempotency_keys_are_per_user(client, make_patient):
    from app.crud import idempotency

    class U:  # two different users sending the same client key
        def __init__(self, i): self.id = i

    class R:
        headers = {"Idempotency-Key": "same"}

    assert idempotency.key_from(R, U(1)) != idempotency.key_from(R, U(2))


def test_note_never_overflows(client, make_patient, protocol_key):
    p = make_patient()
    exam_id = None
    for n in range(1, 60):
        body = _record_body(p["id"], protocol_key, client, exam_id=exam_id)
        body["n_sweeps"] = n
        r = client.post("/api/exams/record", json=body)
        assert r.status_code == 201, r.text
        exam_id = r.json()["id"]
    assert len(r.json()["note"]) <= 512


def test_non_finite_samples_rejected(client, make_patient, protocol_key):
    p = make_patient()
    body = _record_body(p["id"], protocol_key, client)
    import json
    payload = json.dumps(body).replace('"samples": [0.0', '"samples": [NaN')
    r = client.post("/api/exams/record", content=payload,
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_audit_detail_is_clipped(client):
    from app.crud import user as user_crud
    from app.models import AuditLog

    db = SessionLocal()
    try:
        user_crud.audit(db, action="x" * 100, detail="y" * 5000)
        row = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
        assert len(row.detail) <= 256 and len(row.action) <= 48
    finally:
        db.close()


def test_audit_export_streams_csv(client):
    r = client.get("/api/audit/export")
    assert r.status_code == 200
    assert r.text.lstrip("﻿").startswith("at,username,action")
    assert len(r.text.splitlines()) > 2
