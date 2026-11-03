"""Clinical photo gallery (전체사진): upload, list, image delivery and the
pages that embed it, after the gallery was merged into the console UI."""
import io

from PIL import Image


def _png(color=(200, 40, 40), size=(64, 48)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


def test_upload_list_thumb_and_delete(client, make_patient):
    p = make_patient()
    r = client.post("/api/photos", data={"patient_id": p["id"], "eye": "OD",
                                         "modality": "fundus"},
                    files=[("files", ("od.png", _png(), "image/png"))])
    assert r.status_code == 201, r.text
    photos = r.json()
    assert len(photos) == 1 and photos[0]["eye"] == "OD"
    pid = photos[0]["id"]

    rows = client.get(f"/api/photos?patient_id={p['id']}").json()
    assert [x["id"] for x in rows] == [pid]

    img = client.get(f"/api/photos/{pid}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    thumb = client.get(f"/api/photos/{pid}/thumb")
    assert thumb.status_code == 200
    assert Image.open(io.BytesIO(thumb.content)).size[0] <= 512

    assert client.delete(f"/api/photos/{pid}").status_code in (200, 204)
    assert client.get(f"/api/photos?patient_id={p['id']}").json() == []


def test_pages_render_in_console_shell(client, make_patient):
    p = make_patient()
    for url in ("/photos", f"/photos?patient_id={p['id']}", "/photos/viewer?ids=1"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert 'class="rail"' in r.text, url           # console shell, not the old topbar
        assert "#i-photo" in r.text, url               # nav link to 전체사진
    dash = client.get("/dashboard").text
    assert 'href="/photos"' in dash
    detail = client.get(f"/patients/{p['id']}").text
    assert 'id="photo-strip"' in detail
    assert "/photos?patient_id=" in detail
