"""Reception desk (visits, quick search) together with soft delete,
idempotent saves and two-eye live recording."""
import uuid
from datetime import date


def _mrn():
    return f"R-{uuid.uuid4().hex[:8]}"


def _receive(client, **patient):
    body = {"patient": {"mrn": _mrn(), "name": "접수환자", **patient},
            "visit": {"attending_doctor": "김의사", "diagnosis": "RP", "tests": ["ffERG"]}}
    r = client.post("/api/reception", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_reception_creates_patient_and_visit(client):
    out = _receive(client, birth_date="1968-03-02", sex="F")
    assert out["visit"]["patient_id"] == out["patient"]["id"]
    assert out["visit"]["tests"] == ["ffERG"]
    today = client.get("/api/visits").json()
    assert any(v["id"] == out["visit"]["id"] for v in today)


def test_quick_search_by_id_prefix_and_birth_date(client):
    out = _receive(client, birth_date="1971-11-23")
    mrn = out["patient"]["mrn"]
    hits = client.get(f"/api/patients/search?q={mrn[:6]}").json()
    assert any(h["mrn"] == mrn for h in hits)
    hit = next(h for h in client.get("/api/patients/search?q=711123").json() if h["mrn"] == mrn)
    assert hit["visit_count"] == 1 and hit["last_diagnosis"] == "RP"
    # the paginated list understands a typed birth date too
    rows = client.get("/api/patients?q=19711123").json()
    assert any(p["mrn"] == mrn for p in rows)


def test_trashed_patient_leaves_search_and_worklist(client):
    out = _receive(client)
    pid, mrn, vid = out["patient"]["id"], out["patient"]["mrn"], out["visit"]["id"]
    assert client.delete(f"/api/patients/{pid}").status_code == 204
    assert not any(h["id"] == pid for h in client.get(f"/api/patients/search?q={mrn}").json())
    assert not any(v["id"] == vid for v in client.get("/api/visits").json())
    # a new visit for the trashed patient is refused, and so is reusing the ID
    r = client.post("/api/reception", json={"patient_id": pid, "visit": {}})
    assert r.status_code == 404
    r = client.post("/api/reception", json={"patient": {"mrn": mrn, "name": "x"}, "visit": {}})
    assert r.status_code == 409 and "휴지통" in r.json()["detail"]
    assert client.post(f"/api/trash/patients/{pid}/restore").status_code == 200


def test_exam_filed_under_visit_and_hidden_when_trashed(client, protocol_key):
    out = _receive(client)
    pid, vid = out["patient"]["id"], out["visit"]["id"]
    r = client.post("/api/exams", json={"patient_id": pid, "protocol": protocol_key,
                                        "eyes": ["OD"], "visit_id": vid})
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    visit = client.get(f"/api/visits/{vid}").json()
    assert [e["id"] for e in visit["exams"]] == [eid]
    assert client.delete(f"/api/exams/{eid}").status_code == 204
    assert client.get(f"/api/visits/{vid}").json()["exams"] == []


def test_exam_rejects_visit_of_another_patient(client, protocol_key):
    a, b = _receive(client), _receive(client)
    r = client.post("/api/exams", json={"patient_id": a["patient"]["id"], "protocol": protocol_key,
                                        "eyes": ["OD"], "visit_id": b["visit"]["id"]})
    assert r.status_code in (400, 404)


def test_two_eye_live_record_is_idempotent(client):
    out = _receive(client)
    pid, vid = out["patient"]["id"], out["visit"]["id"]
    protos = client.get("/api/protocols/all").json()
    key, proto = next(iter(protos.items()))
    step = proto["steps"][0]
    body = {"patient_id": pid, "protocol": key, "step_key": step["key"], "eye": "OD",
            "samples": [0.0, 1.0, 2.0, 1.0] * 50, "sampling_rate": 1000, "duration_ms": 200,
            "n_sweeps": 30, "n_rejected": 2, "visit_id": vid}
    k_od, k_os = str(uuid.uuid4()), str(uuid.uuid4())
    first = client.post("/api/exams/record", json=body, headers={"Idempotency-Key": k_od}).json()
    eid = first["id"]
    os_body = {**body, "eye": "OS", "exam_id": eid}
    client.post("/api/exams/record", json=os_body, headers={"Idempotency-Key": k_os})
    # the browser retries the whole OU save after a dropped response
    client.post("/api/exams/record", json={**body, "exam_id": eid}, headers={"Idempotency-Key": k_od})
    exam = client.post("/api/exams/record", json=os_body, headers={"Idempotency-Key": k_os}).json()
    assert sorted(w["eye"] for w in exam["waveforms"]) == ["OD", "OS"]
    assert "2 rejected" in exam["note"] and exam["visit_id"] == vid


def test_live_stream_sends_one_row_per_eye(client):
    with client.websocket_connect("/ws/live") as ws:
        meta = ws.receive_json()
        assert meta["signals"] == ["OD", "OS"]
        for _ in range(40):
            m = ws.receive_json()
            if m["type"] == "data":
                assert len(m["samples"]) == 2 and len(m["samples"][0]) == len(m["samples"][1])
                break
        else:
            raise AssertionError("no data message")


def test_dashboard_and_reception_pages_render(client):
    for path in ("/", "/dashboard", "/patients", "/live", "/admin"):
        r = client.get(path)
        assert r.status_code == 200, (path, r.status_code)
    assert date.today().isoformat()
