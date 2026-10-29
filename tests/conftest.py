"""Test configuration: an isolated database, backup and log directory per run.

Settings are read at import time, so the environment is prepared before the
application is imported.
"""
import os
import shutil
import tempfile
import uuid

import pytest

_TMP = tempfile.mkdtemp(prefix="oep-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
    "BACKUP_DIR": f"{_TMP}/backups",
    "BACKUP_MIRROR_DIR": f"{_TMP}/mirror",
    "BACKUP_ENABLED": "0",          # scheduler off; tests call the API directly
    "BACKUP_MIN_FREE_MB": "1",
    "LOG_DIR": f"{_TMP}/logs",
    "SECRET_KEY": "test-secret",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root():
    yield _TMP
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def client(tmp_root):
    with TestClient(app) as c:
        r = c.post("/login", data={"username": "admin", "password": "admin1234"},
                   follow_redirects=False)
        assert r.status_code == 303
        yield c


@pytest.fixture
def make_patient(client):
    def _make(**extra):
        body = {"mrn": f"T-{uuid.uuid4().hex[:10]}", "name": "테스트", **extra}
        r = client.post("/api/patients", json=body)
        assert r.status_code == 201, r.text
        return r.json()
    return _make


@pytest.fixture(scope="session")
def protocol_key(client):
    return next(iter(client.get("/api/protocols/all").json()))
