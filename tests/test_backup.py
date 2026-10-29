"""Backup create / verify / restore, retention policy and disk guard."""
import gzip
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app import backup


def test_backup_roundtrip_and_restore(client, make_patient, tmp_root):
    keep = make_patient(name="백업전")
    r = client.post("/api/backups")
    assert r.status_code == 201, r.text
    info = r.json()
    assert info["integrity"] == "ok"
    assert info["counts"]["patients"] >= 1
    assert info["mirrored"] is True
    assert (Path(tmp_root) / "mirror" / info["name"]).is_file()
    assert client.post(f"/api/backups/{info['name']}/verify").json()["ok"] is True

    later = make_patient(name="백업후")
    # restore requires the backup name as confirmation
    assert client.post(f"/api/backups/{info['name']}/restore",
                       json={"confirm": "yes"}).status_code == 400
    r = client.post(f"/api/backups/{info['name']}/restore", json={"confirm": info["name"]})
    assert r.status_code == 200, r.text
    assert r.json()["pre_restore_backup"].endswith("_pre-restore.db.gz")

    assert client.get(f"/api/patients/{keep['id']}").status_code == 200
    assert client.get(f"/api/patients/{later['id']}").status_code == 404

    # the safety copy taken before the restore still holds the later patient
    pre = r.json()["pre_restore_backup"]
    assert client.post(f"/api/backups/{pre}/verify").json()["ok"] is True
    client.post(f"/api/backups/{pre}/restore", json={"confirm": pre})
    assert client.get(f"/api/patients/{later['id']}").status_code == 200


def test_corrupted_backup_is_detected(client):
    info = client.post("/api/backups").json()
    path = backup.backup_dir() / info["name"]
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF
    path.write_bytes(bytes(data))
    result = client.post(f"/api/backups/{info['name']}/verify")
    assert result.status_code in (200, 400)
    if result.status_code == 200:
        assert result.json()["ok"] is False
    r = client.post(f"/api/backups/{info['name']}/restore", json={"confirm": info["name"]})
    assert r.status_code == 400  # never restore a damaged backup


def test_backup_name_cannot_escape_directory(client):
    assert client.get("/api/backups/..%2F..%2Fetc%2Fpasswd/download").status_code == 404
    with pytest.raises(backup.BackupError):
        backup._resolve("../test.db")


def test_download_is_a_valid_gzip_sqlite(client):
    info = client.post("/api/backups").json()
    r = client.get(f"/api/backups/{info['name']}/download")
    assert r.status_code == 200
    assert gzip.decompress(r.content)[:16] == b"SQLite format 3\x00"


def test_disk_guard(monkeypatch):
    class Usage:
        free = 10 * 1024 * 1024
    monkeypatch.setattr(backup.shutil, "disk_usage", lambda p: Usage)
    monkeypatch.setattr(backup.settings, "BACKUP_MIN_FREE_MB", 500)
    with pytest.raises(backup.BackupError, match="여유 공간"):
        backup.create_backup("manual")
    assert backup.status()["last_error"]


def test_retention_policy(monkeypatch):
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_ALL_DAYS", 3)
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_DAILY_DAYS", 30)
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_MONTHLY", 6)
    now = datetime(2026, 10, 28, 12, 0, 0)
    entries = []
    for h in range(0, 24 * 400, 6):  # a backup every 6 h for ~400 days
        ts = now - timedelta(hours=h)
        entries.append({"name": f"b{h}", "ts": ts, "tag": "auto"})
    entries.append({"name": "safety", "ts": now - timedelta(days=300), "tag": "pre-restore"})
    entries.sort(key=lambda e: e["ts"], reverse=True)
    keep = backup.select_keep(entries, now)

    assert "safety" in keep
    assert entries[0]["name"] in keep
    recent = [e for e in entries if now - e["ts"] <= timedelta(days=3) and e["tag"] == "auto"]
    assert all(e["name"] in keep for e in recent)
    days_kept = {e["ts"].date() for e in entries if e["name"] in keep
                 and timedelta(days=3) < now - e["ts"] <= timedelta(days=30)}
    assert len(days_kept) >= 26
    old = [e for e in entries if e["name"] in keep and now - e["ts"] > timedelta(days=200)]
    assert [e["name"] for e in old] == ["safety"]
    assert len(keep) < 60


def test_prune_never_empties(tmp_path, monkeypatch):
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_ALL_DAYS", 0)
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_DAILY_DAYS", 0)
    monkeypatch.setattr(backup.settings, "BACKUP_KEEP_MONTHLY", 0)
    (tmp_path / "oep_20200101-000000_auto.db.gz").write_bytes(b"x")
    (tmp_path / "oep_20200102-000000_auto.db.gz").write_bytes(b"x")
    removed = backup.prune(tmp_path)
    assert removed == ["oep_20200101-000000_auto.db.gz"]
    assert (tmp_path / "oep_20200102-000000_auto.db.gz").exists()


def test_scheduler_takes_due_backup(client, monkeypatch):
    calls = []
    monkeypatch.setattr(backup, "backup_due", lambda now=None: True)
    monkeypatch.setattr(backup, "create_backup",
                        lambda tag, only_if_due=False: calls.append(tag) or {"name": "x"})
    backup.BackupScheduler().tick()
    assert calls == ["auto"]


def test_system_status_reports_backups(client):
    s = client.get("/api/system/status").json()
    assert s["database"]["journal_mode"] == "wal"
    assert s["backup"]["supported"] is True
    assert isinstance(s["warnings"], list)
    assert client.post("/api/system/integrity").json()["ok"] is True


def test_cli_list(capsys):
    assert backup.main(["list"]) == 0
    assert "oep_" in capsys.readouterr().out
