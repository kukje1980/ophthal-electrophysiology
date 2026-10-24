"""Manual marker review and report sign-off."""
from app.iscev import detect_markers, remeasure


def _wf(exam, step, eye="OD"):
    return next(w for w in exam["waveforms"] if w["step"] == step and w["eye"] == eye)


def _m(wf, marker):
    return next(m for m in wf["measurements"] if m["marker"] == marker)


def test_remeasure_matches_auto_detection():
    t = [i / 2.0 for i in range(500)]  # 2 kHz, 250 ms
    y = [(-100 if 10 <= x <= 20 else 0) + (200 if 40 <= x <= 50 else 0) for x in t]
    auto = detect_markers(y, 250, "DA3.0", ["a", "b"])
    again = remeasure(y, 250, "DA3.0", {m["marker"]: m["latency_ms"] for m in auto})
    assert [(m["marker"], m["amplitude_uv"]) for m in auto] == \
           [(m["marker"], m["amplitude_uv"]) for m in again]


def test_edit_marker_recomputes_dependent_amplitude(client, exam):
    wf = _wf(exam, "DA3.0")
    a_lat = _m(wf, "a")["latency_ms"]
    url = f"/api/exams/{exam['id']}/waveforms/{wf['id']}/markers/a"
    r = client.put(url, json={"latency_ms": 5.0, "snap": False})
    assert r.status_code == 200, r.text
    out = r.json()
    a = _m(out, "a")
    assert a["latency_ms"] == 5.0 and a["is_auto"] is False
    # b is measured from a, so its amplitude changes too (but stays auto)
    assert _m(out, "b")["amplitude_uv"] != _m(wf, "b")["amplitude_uv"]
    assert _m(out, "b")["is_auto"] is True

    # snapping pulls a nearby click back onto the trough
    r = client.put(url, json={"latency_ms": a_lat + 2, "snap": True})
    assert abs(_m(r.json(), "a")["latency_ms"] - a_lat) <= 1.0

    # reset restores automatic detection
    r = client.post(f"/api/exams/{exam['id']}/waveforms/{wf['id']}/markers/reset")
    assert {m["marker"] for m in r.json()["measurements"]} == {"a", "b"}
    assert all(m["is_auto"] for m in r.json()["measurements"])


def test_edit_marker_validation(client, exam):
    wf = _wf(exam, "DA3.0")
    base = f"/api/exams/{exam['id']}/waveforms/{wf['id']}/markers"
    assert client.put(f"{base}/P100", json={"latency_ms": 20}).status_code == 400
    assert client.put(f"{base}/a", json={"latency_ms": -1}).status_code == 400
    assert client.put(f"/api/exams/{exam['id']}/waveforms/999999/markers/a",
                      json={"latency_ms": 20}).status_code == 404


def test_remove_marker(client, exam):
    wf = _wf(exam, "DA3.0")
    r = client.delete(f"/api/exams/{exam['id']}/waveforms/{wf['id']}/markers/a")
    assert r.status_code == 200
    assert "a" not in {m["marker"] for m in r.json()["measurements"]}


def test_sign_locks_and_reopen_unlocks(client, exam):
    eid = exam["id"]
    wf = _wf(exam, "DA3.0")
    edit = f"/api/exams/{eid}/waveforms/{wf['id']}/markers/a"

    assert client.post(f"/api/exams/{eid}/sign", json={}).status_code == 400
    r = client.put(f"/api/exams/{eid}/interpretation",
                   json={"interpretation": "Normal scotopic and photopic ERG."})
    assert r.json()["interpretation"].startswith("Normal")

    r = client.post(f"/api/exams/{eid}/sign", json={})
    assert r.status_code == 200
    assert r.json()["status"] == "signed" and r.json()["signed_by"]

    assert client.put(edit, json={"latency_ms": 15}).status_code == 409
    assert client.put(f"/api/exams/{eid}/interpretation",
                      json={"interpretation": "x"}).status_code == 409
    assert client.post(f"/api/exams/{eid}/sign", json={}).status_code == 409

    r = client.post(f"/api/exams/{eid}/reopen")
    assert r.status_code == 200 and r.json()["signed_at"] is None
    assert client.put(edit, json={"latency_ms": 15}).status_code == 200


def test_technician_cannot_sign(client, exam):
    client.post("/api/users", json={"username": "tech1", "password": "techpass123",
                                    "role": "technician"})
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as tech:
        tech.post("/login", data={"username": "tech1", "password": "techpass123"})
        r = tech.post(f"/api/exams/{exam['id']}/sign",
                      json={"interpretation": "x"})
        assert r.status_code == 403
        wf = _wf(exam, "DA3.0")
        r = tech.put(f"/api/exams/{exam['id']}/waveforms/{wf['id']}/markers/a",
                     json={"latency_ms": 15})
        assert r.status_code == 200
