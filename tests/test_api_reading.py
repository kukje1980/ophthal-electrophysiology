"""API tests: acquisition, cursor editing, analysis, interpretation, sign-off, RBAC."""
from tests.conftest import run_exam


def _wf(exam, eye="OD", step="PR_1deg"):
    return next(w for w in exam["waveforms"] if w["eye"] == eye and w["step"] == step)


def _m(wf, marker):
    return next(m for m in wf["measurements"] if m["marker"] == marker)


def test_run_exam_detects_markers_for_both_eyes(client, vep_exam):
    assert vep_exam["status"] == "completed"
    assert vep_exam["signed_by"] is None
    assert {w["eye"] for w in vep_exam["waveforms"]} == {"OD", "OS"}
    assert {w["step"] for w in vep_exam["waveforms"]} == {"PR_1deg", "PR_0.25deg"}
    for wf in vep_exam["waveforms"]:
        assert {m["marker"] for m in wf["measurements"]} == {"N75", "P100", "N145"}
        assert all(m["is_auto"] for m in wf["measurements"])


def test_move_marker_recomputes_dependents_and_marks_manual(client, vep_exam):
    wf = _wf(vep_exam)
    n75, p100 = _m(wf, "N75"), _m(wf, "P100")
    r = client.put(f"/api/measurements/{n75['id']}", json={"latency_ms": 88})
    assert r.status_code == 200
    assert r.json()["latency_ms"] == 88.0 and r.json()["is_auto"] is False

    wf2 = _wf(client.get(f"/api/exams/{vep_exam['id']}").json())
    assert _m(wf2, "P100")["is_auto"] is True            # untouched cursor stays auto
    assert _m(wf2, "P100")["amplitude_uv"] != p100["amplitude_uv"]  # but re-measured


def test_move_marker_clamps_into_trace(client, vep_exam):
    m = _m(_wf(vep_exam), "N145")
    r = client.put(f"/api/measurements/{m['id']}", json={"latency_ms": 5000})
    assert r.status_code == 200
    assert r.json()["latency_ms"] <= _wf(vep_exam)["duration_ms"]
    assert client.put(f"/api/measurements/{m['id']}", json={"latency_ms": -1}).status_code == 422


def test_add_delete_redetect(client, vep_exam):
    wf = _wf(vep_exam, eye="OS")
    # unknown marker name is rejected
    r = client.post(f"/api/waveforms/{wf['id']}/measurements",
                    json={"marker": "ZZZ", "latency_ms": 50})
    assert r.status_code == 400
    # placing an existing marker by hand replaces it
    r = client.post(f"/api/waveforms/{wf['id']}/measurements",
                    json={"marker": "P100", "latency_ms": 118})
    assert r.status_code == 201
    assert r.json()["latency_ms"] == 118.0 and r.json()["is_auto"] is False
    assert r.json()["flag"] == "abnormal"       # 118 ms > 115 ms limit (demo range)
    # delete
    r = client.delete(f"/api/measurements/{r.json()['id']}")
    assert r.status_code == 204
    wf2 = _wf(client.get(f"/api/exams/{vep_exam['id']}").json(), eye="OS")
    assert {m["marker"] for m in wf2["measurements"]} == {"N75", "N145"}
    # auto re-detect restores the standard set
    r = client.post(f"/api/waveforms/{wf['id']}/redetect")
    assert r.status_code == 200
    assert {m["marker"] for m in r.json()["measurements"]} == {"N75", "P100", "N145"}
    assert all(m["is_auto"] for m in r.json()["measurements"])


def test_analysis_endpoint_reports_asymmetry(client, vep_exam):
    wf = _wf(vep_exam, eye="OS")
    client.post(f"/api/waveforms/{wf['id']}/measurements",
                json={"marker": "P100", "latency_ms": 120})
    a = client.get(f"/api/exams/{vep_exam['id']}/analysis").json()
    assert a["overall"] == "abnormal"
    inter = {x["marker"]: x for x in a["steps"][0]["interocular"]}
    assert inter["P100"]["lat_flag"] == "abnormal"
    assert inter["P100"]["slower_eye"] == "OS"
    assert any("P100" in line for line in a["summary"])
    assert "limits" in inter["P100"]


def test_interpretation_sign_lock_reopen(client, vep_exam):
    eid = vep_exam["id"]
    r = client.put(f"/api/exams/{eid}/interpretation",
                   json={"interpretation": "P100 정상 범위", "impression": "정상 VEP"})
    assert r.status_code == 200
    assert r.json()["interpreted_by"] == "System Administrator"
    assert r.json()["interpreted_at"]

    # worklist shows it as unsigned
    ids = [e["id"] for e in client.get("/api/exams?unsigned=true").json()]
    assert eid in ids

    r = client.post(f"/api/exams/{eid}/sign")
    assert r.status_code == 200
    assert r.json()["status"] == "signed" and r.json()["signed_by"]
    assert eid not in [e["id"] for e in client.get("/api/exams?unsigned=true").json()]

    # locked: markers, interpretation, deletion, appending live traces
    m = _m(_wf(vep_exam), "P100")
    assert client.put(f"/api/measurements/{m['id']}", json={"latency_ms": 90}).status_code == 409
    assert client.post(f"/api/waveforms/{_wf(vep_exam)['id']}/redetect").status_code == 409
    assert client.put(f"/api/exams/{eid}/interpretation",
                      json={"interpretation": "x"}).status_code == 409
    assert client.delete(f"/api/exams/{eid}").status_code == 409
    assert client.post(f"/api/exams/{eid}/sign").status_code == 409
    rec = client.post("/api/exams/record", json={
        "patient_id": vep_exam["patient_id"], "protocol": "VEP_pattern_reversal",
        "step_key": "PR_1deg", "eye": "OD", "samples": [0.0] * 300,
        "sampling_rate": 1000, "duration_ms": 300, "exam_id": eid})
    assert rec.status_code == 409

    # reopen -> editable again
    r = client.post(f"/api/exams/{eid}/reopen")
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["signed_by"] is None
    assert client.put(f"/api/measurements/{m['id']}", json={"latency_ms": 90}).status_code == 200
    assert client.post(f"/api/exams/{eid}/reopen").status_code == 409

    actions = {a["action"] for a in client.get("/api/audit").json()}
    assert {"exam.interpret", "exam.sign", "exam.reopen", "marker.move"} <= actions


def test_csv_export(client, vep_exam):
    r = client.get(f"/api/exams/{vep_exam['id']}/export.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("exam_id,patient_id,test_type,protocol,step,eye,marker")
    assert len(lines) == 1 + 2 * 2 * 3     # 2 steps x 2 eyes x 3 markers


def test_rbac_for_reading_workflow(client, staff, patient):
    exam = run_exam(client, patient["id"])
    eid = exam["id"]
    m = _m(_wf(exam), "P100")

    tech, viewer, doc = staff["technician"], staff["viewer"], staff["clinician"]
    # technician: may edit cursors but not interpret or sign
    assert tech.put(f"/api/measurements/{m['id']}", json={"latency_ms": 99}).status_code == 200
    assert tech.put(f"/api/exams/{eid}/interpretation", json={"impression": "x"}).status_code == 403
    assert tech.post(f"/api/exams/{eid}/sign").status_code == 403
    # viewer: read-only
    assert viewer.get(f"/api/exams/{eid}/analysis").status_code == 200
    assert viewer.put(f"/api/measurements/{m['id']}", json={"latency_ms": 99}).status_code == 403
    assert viewer.post(f"/api/exams/{eid}/sign").status_code == 403
    # clinician: full reading workflow, and the signature carries their name
    assert doc.put(f"/api/exams/{eid}/interpretation", json={"impression": "정상"}).status_code == 200
    r = doc.post(f"/api/exams/{eid}/sign")
    assert r.status_code == 200 and r.json()["signed_by"] == "clinician"
    assert tech.put(f"/api/measurements/{m['id']}", json={"latency_ms": 97}).status_code == 409
    assert tech.post(f"/api/exams/{eid}/reopen").status_code == 403


def test_report_page_renders_for_viewer(client, staff, vep_exam):
    r = staff["viewer"].get(f"/reports/{vep_exam['id']}")
    assert r.status_code == 200
    assert "판독 소견" in r.text
    assert "edit_markers" not in r.text.split("const PERMS = ")[1].split(";")[0]
    r = client.get("/dashboard")  # "/" is the reception screen
    assert r.status_code == 200 and "판독 대기" in r.text


def test_trashed_exam_leaves_worklist_and_cannot_be_edited(client, vep_exam):
    eid = vep_exam["id"]
    wf = vep_exam["waveforms"][0]
    mid = wf["measurements"][0]["id"]
    assert any(e["id"] == eid for e in client.get("/api/exams?unsigned=true").json())
    assert client.delete(f"/api/exams/{eid}").status_code == 204
    assert not any(e["id"] == eid for e in client.get("/api/exams?unsigned=true").json())
    assert client.put(f"/api/measurements/{mid}", json={"latency_ms": 100}).status_code == 404
    assert client.delete(f"/api/measurements/{mid}").status_code == 404
    assert client.post(f"/api/waveforms/{wf['id']}/redetect").status_code == 404
    assert client.post(f"/api/trash/exams/{eid}/restore").status_code == 200
    assert client.put(f"/api/measurements/{mid}", json={"latency_ms": 100}).status_code == 200
