"""Clinical photo gallery (전체사진): upload, list, image/thumb, pages, RBAC."""
import io
import os

from PIL import Image

from app.config import settings


def _jpeg(color=(200, 60, 30)):
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), color).save(buf, "JPEG")
    return buf.getvalue()


def _upload(client, patient_id, eye="OD", **fields):
    r = client.post("/api/photos",
                    data={"patient_id": str(patient_id), "eye": eye,
                          "modality": "fundus", **fields},
                    files=[("files", (f"{eye}.jpg", _jpeg(), "image/jpeg"))])
    assert r.status_code in (200, 201), r.text
    body = r.json()
    return body[0] if isinstance(body, list) else body


def test_upload_list_image_and_delete(client, patient):
    p = _upload(client, patient["id"], note="테스트 안저")
    assert p["eye"] == "OD" and p["patient_id"] == patient["id"]

    rows = client.get(f"/api/photos?patient_id={patient['id']}").json()
    assert [x["id"] for x in rows] == [p["id"]]

    assert client.get(f"/api/photos/{p['id']}/thumb").status_code == 200
    img = client.get(f"/api/photos/{p['id']}/image")
    assert img.status_code == 200
    assert Image.open(io.BytesIO(img.content)).size == (320, 240)

    # Files are stored encrypted under PHOTO_DIR: nothing on disk decodes as JPEG
    for root, _, files in os.walk(settings.PHOTO_DIR):
        for f in files:
            with open(os.path.join(root, f), "rb") as fh:
                assert not fh.read(3).startswith(b"\xff\xd8\xff")

    r = client.put(f"/api/photos/{p['id']}", json={"note": "수정됨", "eye": "OS"})
    assert r.status_code == 200 and r.json()["note"] == "수정됨"

    assert client.delete(f"/api/photos/{p['id']}").status_code in (200, 204)
    assert client.get(f"/api/photos/{p['id']}/thumb").status_code == 404


def test_pages_render_with_gallery_entry(client, patient):
    p = _upload(client, patient["id"])
    for path in ("/photos", f"/photos?patient_id={patient['id']}",
                 f"/photos/viewer?ids={p['id']}", "/dashboard",
                 f"/patients/{patient['id']}"):
        r = client.get(path)
        assert r.status_code == 200, path
        assert "전체사진" in r.text, path
    assert "photo-strip" in client.get(f"/patients/{patient['id']}").text


def test_viewer_cannot_upload_or_delete(client, staff, patient):
    p = _upload(client, patient["id"])
    viewer = staff["viewer"]
    assert viewer.get(f"/api/photos/{p['id']}/thumb").status_code == 200
    r = viewer.post("/api/photos", data={"patient_id": str(patient["id"])},
                    files=[("files", ("x.jpg", _jpeg(), "image/jpeg"))])
    assert r.status_code == 403
    assert viewer.delete(f"/api/photos/{p['id']}").status_code == 403
    # technicians may upload but not delete
    tech = staff["technician"]
    q = _upload(tech, patient["id"], eye="OS")
    assert tech.delete(f"/api/photos/{q['id']}").status_code == 403
