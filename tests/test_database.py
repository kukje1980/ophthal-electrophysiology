"""Database durability settings, indexes and additive migration."""
from sqlalchemy import inspect, text

from app.database import engine


def test_sqlite_durability_pragmas(client):
    with engine.connect() as conn:
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"
        assert conn.execute(text("PRAGMA synchronous")).scalar() == 2  # FULL
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA busy_timeout")).scalar() >= 5000


def test_indexes_for_growing_tables(client):
    insp = inspect(engine)
    patient_ix = {tuple(ix["column_names"]) for ix in insp.get_indexes("patients")}
    exam_ix = {tuple(ix["column_names"]) for ix in insp.get_indexes("exams")}
    assert ("deleted_at", "created_at") in patient_ix
    assert ("patient_id", "performed_at") in exam_ix
    assert ("deleted_at", "performed_at") in exam_ix


def test_patient_list_uses_index_not_sort(client):
    sql = ("EXPLAIN QUERY PLAN SELECT id FROM patients WHERE deleted_at IS NULL "
           "ORDER BY created_at DESC, id DESC LIMIT 50")
    with engine.connect() as conn:
        plan = " ".join(str(r[-1]) for r in conn.execute(text(sql)))
    assert "ix_patients_active_created" in plan
    assert "TEMP B-TREE" not in plan


def test_foreign_keys_enforced(client):
    import pytest
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text(
                "INSERT INTO waveforms (exam_id, eye, step, sampling_rate, "
                "duration_ms, samples) VALUES (999999, 'OD', 'x', 1000, 10, '[]')"))


def test_health_is_public(client):
    from fastapi.testclient import TestClient

    from app.main import app

    anon = TestClient(app)  # no session cookie
    r = anon.get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"
    assert anon.get("/api/patients").status_code == 401
