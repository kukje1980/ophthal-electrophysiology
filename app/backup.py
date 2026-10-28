"""Database backup: consistent online snapshots, verification, retention,
an off-disk mirror and restore.

Each backup is a gzip-compressed SQLite snapshot plus a JSON manifest::

    backups/oep_20261028-143000_auto.db.gz
    backups/oep_20261028-143000_auto.json    (sha256, sizes, row counts, integrity)

* Snapshots use SQLite's online backup API, so they are consistent while the
  application keeps running (no need to stop the server).
* Every snapshot is integrity-checked before it is kept; a failed check is
  reported as possible corruption of the live database.
* Files are written to a temporary name, fsync'ed and atomically renamed, so a
  crash or power cut mid-backup never leaves a half-written backup behind.
* ``BACKUP_MIRROR_DIR`` receives a verified second copy (NAS / USB / second
  disk), so a disk failure does not take the backups with it.
* Restore first verifies the backup, then saves a ``pre-restore`` safety copy
  of the current database, then copies the snapshot into the live database
  through SQLite itself.

Command line (also works while the server is down)::

    python -m app.backup create
    python -m app.backup list
    python -m app.backup verify  <name>
    python -m app.backup restore <name>
    python -m app.backup prune
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

from app.config import settings
from app.database import engine, sqlite_path

log = logging.getLogger("app.backup")

_SUFFIX = ".db.gz"
_NAME_RE = re.compile(r"^oep_(\d{8}-\d{6})_([a-z-]+)\.db\.gz$")
_TS_FMT = "%Y%m%d-%H%M%S"
#: safety copies taken automatically before a restore / schema upgrade; never
#: pruned automatically
PROTECTED_TAGS = {"pre-restore", "pre-migration"}
TAGS = {"auto", "manual"} | PROTECTED_TAGS
_COUNT_TABLES = ("patients", "exams", "waveforms", "measurements",
                 "users", "audit_logs", "reference_ranges")
_STATUS_FILE = "status.json"

_thread_lock = threading.Lock()


class BackupError(RuntimeError):
    """A backup / verify / restore could not be completed."""


class BackupBusy(BackupError):
    """Another backup or restore is already running."""


# -- locations --------------------------------------------------------------

def supported() -> bool:
    """Built-in backups cover the SQLite deployment (other databases use their
    own dump tools, e.g. pg_dump)."""
    return sqlite_path() is not None


def backup_dir() -> Path:
    d = Path(settings.BACKUP_DIR).resolve()
    d.mkdir(parents=True, exist_ok=True)
    return d


def mirror_dir() -> Optional[Path]:
    return Path(settings.BACKUP_MIRROR_DIR).resolve() if settings.BACKUP_MIRROR_DIR else None


def _manifest_path(path: Path) -> Path:
    return path.with_name(path.name[:-len(_SUFFIX)] + ".json")


def _resolve(name: str, directory: Optional[Path] = None) -> Path:
    """Validated path of a backup file (rejects anything but our own names,
    which also rules out path traversal)."""
    if not _NAME_RE.match(name or ""):
        raise BackupError(f"잘못된 백업 이름입니다: {name!r}")
    path = (directory or backup_dir()) / name
    if not path.is_file():
        raise BackupError(f"백업 파일이 없습니다: {name}")
    return path


# -- low-level helpers --------------------------------------------------------

@contextmanager
def _exclusive():
    """One backup / restore at a time, across threads and across server
    processes (several workers or the CLI share the backup directory)."""
    if not _thread_lock.acquire(blocking=False):
        raise BackupBusy("다른 백업/복원 작업이 진행 중입니다.")
    fh = None
    try:
        fh = open(backup_dir() / ".lock", "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            raise BackupBusy("다른 백업/복원 작업이 진행 중입니다.") from e
        yield
    finally:
        if fh is not None:
            if os.name == "nt":
                try:
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            fh.close()  # releases flock
        _thread_lock.release()


def _fsync_file(path: Path) -> None:
    with open(path, "rb+") as f:
        os.fsync(f.fileno())


def _fsync_dir(path: Path) -> None:
    """Persist a rename (POSIX; Windows has no directory fsync)."""
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json_atomic(path: Path, data: dict) -> None:
    tmp = path.with_name(path.name + ".part")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _read_json(path: Path) -> Optional[dict]:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _db_size(path: Path) -> int:
    size = path.stat().st_size
    wal = path.with_name(path.name + "-wal")
    if wal.exists():
        size += wal.stat().st_size
    return size


def _check_space(directory: Path, needed: int) -> None:
    """Refuse to write when it would leave less than BACKUP_MIN_FREE_MB — a
    backup must never fill the disk the live database is on."""
    free = shutil.disk_usage(directory).free
    reserve = settings.BACKUP_MIN_FREE_MB * 1024 * 1024
    if free - needed < reserve:
        raise BackupError(
            f"디스크 여유 공간 부족 ({directory}): {free / 2**20:.0f} MB 남음, "
            f"필요 {(needed + reserve) / 2**20:.0f} MB")


def _cleanup_stale_temp(directory: Path) -> None:
    """Remove leftovers of a backup interrupted by a crash / power cut."""
    cutoff = time.time() - 3600
    for p in list(directory.glob(".tmp-*")) + list(directory.glob("*.part")):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def _inspect(db_path: Path) -> Dict:
    """Integrity check + row counts of a standalone SQLite file."""
    con = sqlite3.connect(str(db_path))
    try:
        rows = [r[0] for r in con.execute("PRAGMA integrity_check").fetchall()]
        counts = {}
        for t in _COUNT_TABLES:
            try:
                counts[t] = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                pass
    finally:
        con.close()
    integrity = "ok" if rows == ["ok"] else "; ".join(rows[:10])
    return {"integrity": integrity, "counts": counts}


def _snapshot(src_path: Path, dst_path: Path) -> None:
    """Consistent copy of the live database via the online backup API,
    converted to one self-contained file (no -wal / -shm companions)."""
    src = sqlite3.connect(str(src_path), timeout=60)
    dst = sqlite3.connect(str(dst_path))
    try:
        src.backup(dst)
        dst.execute("PRAGMA journal_mode=DELETE")
    finally:
        dst.close()
        src.close()


def _gzip(src: Path, dst: Path) -> None:
    with open(src, "rb") as fin, gzip.open(dst, "wb", compresslevel=6) as fout:
        shutil.copyfileobj(fin, fout, 1 << 20)
    _fsync_file(dst)


def _gunzip(src: Path, dst: Path) -> None:
    try:
        with gzip.open(src, "rb") as fin, open(dst, "wb") as fout:
            shutil.copyfileobj(fin, fout, 1 << 20)
    except (OSError, EOFError) as e:
        raise BackupError(f"백업 파일 압축 해제 실패 (손상 가능성): {e}") from e


def _parse(path: Path) -> Optional[Dict]:
    m = _NAME_RE.match(path.name)
    if not m:
        return None
    ts = datetime.strptime(m.group(1), _TS_FMT)
    entry = {"name": path.name, "ts": ts, "tag": m.group(2),
             "created_at": ts.isoformat(timespec="seconds"),
             "size": path.stat().st_size, "integrity": "unknown"}
    manifest = _read_json(_manifest_path(path))
    if manifest:
        entry.update({k: manifest[k] for k in
                      ("sha256", "db_size", "integrity", "counts", "mirrored",
                       "mirror_error", "duration_s") if k in manifest})
    return entry


# -- status file -------------------------------------------------------------

def _record_status(*, success: Optional[Dict] = None, error: Optional[str] = None) -> None:
    path = backup_dir() / _STATUS_FILE
    st = _read_json(path) or {}
    now = datetime.now().isoformat(timespec="seconds")
    st["last_attempt"] = now
    if success is not None:
        st.update(last_success=now, last_name=success["name"],
                  last_error=None, last_error_at=None)
    if error is not None:
        st.update(last_error=error, last_error_at=now)
    try:
        _write_json_atomic(path, st)
    except OSError:
        log.exception("could not write backup status file")


# -- public API --------------------------------------------------------------

def list_backups(directory: Optional[Path] = None) -> List[Dict]:
    """All backups, newest first."""
    d = directory or backup_dir()
    if not d.is_dir():
        return []
    entries = [e for e in (_parse(p) for p in d.glob("oep_*" + _SUFFIX)) if e]
    entries.sort(key=lambda e: e["ts"], reverse=True)
    return entries


def create_backup(tag: str = "manual", only_if_due: bool = False) -> Optional[Dict]:
    """Write a verified, compressed snapshot of the live database (and its
    mirror copy), prune old backups and return the manifest.

    ``only_if_due`` re-checks ``backup_due()`` once the lock is held, so
    several server processes never take the same scheduled backup twice
    (returns None when another process already did)."""
    if tag not in TAGS:
        raise ValueError(f"unknown backup tag {tag!r}")
    src = sqlite_path()
    if src is None:
        raise BackupError("내장 백업은 SQLite 데이터베이스만 지원합니다 "
                          "(PostgreSQL 등은 pg_dump로 백업하세요).")
    if not src.exists():
        raise BackupError(f"데이터베이스 파일이 없습니다: {src}")
    try:
        with _exclusive():
            if only_if_due and not backup_due():
                return None
            info = _create_locked(src, tag)
    except BackupBusy:
        raise
    except Exception as e:  # noqa: BLE001 - record every failure for the admin
        msg = str(e) if isinstance(e, BackupError) else f"{type(e).__name__}: {e}"
        _record_status(error=msg)
        log.error("backup failed: %s", msg)
        if isinstance(e, BackupError):
            raise
        raise BackupError(msg) from e
    _record_status(success=info)
    return info


def _create_locked(src: Path, tag: str) -> Dict:
    started = time.time()
    bdir = backup_dir()
    _cleanup_stale_temp(bdir)

    now = datetime.now().replace(microsecond=0)
    name = f"oep_{now.strftime(_TS_FMT)}_{tag}{_SUFFIX}"
    while (bdir / name).exists():  # two backups within the same second
        now += timedelta(seconds=1)
        name = f"oep_{now.strftime(_TS_FMT)}_{tag}{_SUFFIX}"

    _check_space(bdir, needed=2 * _db_size(src))
    tmp_db = bdir / f".tmp-{os.getpid()}-{threading.get_ident()}.db"
    final = bdir / name
    part = bdir / (name + ".part")
    try:
        _snapshot(src, tmp_db)
        check = _inspect(tmp_db)
        if check["integrity"] != "ok":
            raise BackupError("무결성 검사 실패 — 데이터베이스 손상 가능성이 있습니다: "
                              + check["integrity"])
        db_size = tmp_db.stat().st_size
        _gzip(tmp_db, part)
        os.replace(part, final)
        manifest = {
            "name": name, "created_at": now.isoformat(timespec="seconds"),
            "tag": tag, "source": str(src), "db_size": db_size,
            "size": final.stat().st_size, "sha256": _sha256(final),
            "integrity": "ok", "counts": check["counts"],
            "mirrored": False, "mirror_error": None,
        }
        _write_json_atomic(_manifest_path(final), manifest)
        _fsync_dir(bdir)
    except BaseException:
        for p in (part, final, _manifest_path(final)):
            try:
                p.unlink()
            except OSError:
                pass
        raise
    finally:
        try:
            tmp_db.unlink()
        except OSError:
            pass

    mdir = mirror_dir()
    if mdir is not None:
        try:
            _mirror(final, manifest, mdir)
            manifest["mirrored"] = True
        except Exception as e:  # noqa: BLE001 - the primary copy is still good
            manifest["mirror_error"] = f"{type(e).__name__}: {e}"
            log.error("backup mirror to %s failed: %s", mdir, e)
    manifest["duration_s"] = round(time.time() - started, 2)
    _write_json_atomic(_manifest_path(final), manifest)

    prune(bdir)
    if mdir is not None and mdir.is_dir():
        try:
            prune(mdir)
        except OSError as e:
            log.error("pruning mirror %s failed: %s", mdir, e)
    log.info("backup written: %s (%.1f MB, %ss)", name,
             manifest["size"] / 2**20, manifest["duration_s"])
    return manifest


def _mirror(path: Path, manifest: Dict, mdir: Path) -> None:
    """Copy a backup to the mirror directory and verify the copy's checksum."""
    mdir.mkdir(parents=True, exist_ok=True)
    _check_space(mdir, needed=path.stat().st_size)
    part = mdir / (path.name + ".part")
    shutil.copyfile(path, part)
    _fsync_file(part)
    if _sha256(part) != manifest["sha256"]:
        part.unlink()
        raise BackupError("미러 사본의 체크섬이 일치하지 않습니다")
    os.replace(part, mdir / path.name)
    _write_json_atomic(_manifest_path(mdir / path.name), {**manifest, "mirrored": True})
    _fsync_dir(mdir)


def verify_backup(name: str, directory: Optional[Path] = None) -> Dict:
    """Check a backup end-to-end: checksum, decompression and SQLite integrity."""
    path = _resolve(name, directory)
    manifest = _read_json(_manifest_path(path)) or {}
    sha_ok = None
    if manifest.get("sha256"):
        sha_ok = _sha256(path) == manifest["sha256"]
    tmp = path.with_name(f".tmp-verify-{os.getpid()}-{threading.get_ident()}.db")
    try:
        _check_space(path.parent, needed=manifest.get("db_size") or 4 * path.stat().st_size)
        _gunzip(path, tmp)
        check = _inspect(tmp)
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass
    ok = sha_ok is not False and check["integrity"] == "ok"
    return {"name": name, "ok": ok, "sha256_ok": sha_ok,
            "integrity": check["integrity"], "counts": check["counts"]}


def restore_backup(name: str) -> Dict:
    """Replace the live database with a backup.

    The backup is verified first and a ``pre-restore`` copy of the current
    database is saved, so a restore can itself be undone. Run ``init_db()``
    afterwards to bring an older backup's schema up to date.
    """
    live = sqlite_path()
    if live is None:
        raise BackupError("내장 복원은 SQLite 데이터베이스만 지원합니다.")
    with _exclusive():
        path = _resolve(name)
        manifest = _read_json(_manifest_path(path)) or {}
        if manifest.get("sha256") and _sha256(path) != manifest["sha256"]:
            raise BackupError("백업 파일 체크섬 불일치 — 손상된 백업은 복원할 수 없습니다.")
        bdir = backup_dir()
        tmp = bdir / f".tmp-restore-{os.getpid()}.db"
        try:
            _check_space(bdir, needed=(manifest.get("db_size") or 4 * path.stat().st_size)
                         + (2 * _db_size(live) if live.exists() else 0))
            _gunzip(path, tmp)
            check = _inspect(tmp)
            if check["integrity"] != "ok":
                raise BackupError("백업 무결성 검사 실패 — 복원을 중단했습니다: "
                                  + check["integrity"])
            pre = _create_locked(live, "pre-restore") if live.exists() else None
            if pre:
                _record_status(success=pre)

            # Copy through SQLite (not a file swap) so the WAL is handled and
            # the server's open connections remain valid.
            engine.dispose()
            src = sqlite3.connect(str(tmp))
            dst = sqlite3.connect(str(live), timeout=60)
            try:
                src.backup(dst)
            finally:
                src.close()
                dst.close()
            engine.dispose()
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
    log.warning("database restored from %s (safety copy: %s)", name,
                pre["name"] if pre else "-")
    return {"restored": name, "counts": check["counts"],
            "pre_restore_backup": pre["name"] if pre else None}


# -- retention ---------------------------------------------------------------

def _months_between(a: datetime, b: datetime) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def select_keep(entries: List[Dict], now: Optional[datetime] = None) -> set:
    """Names to keep: every backup of the last BACKUP_KEEP_ALL_DAYS days, the
    newest per day for BACKUP_KEEP_DAILY_DAYS, the newest per month for
    BACKUP_KEEP_MONTHLY months, all protected safety copies, and always the
    newest backup. ``entries`` must be newest first."""
    now = now or datetime.now()
    keep = set()
    if not entries:
        return keep
    keep.add(entries[0]["name"])
    seen_days, seen_months = set(), set()
    for e in entries:
        ts = e["ts"]
        if e["tag"] in PROTECTED_TAGS:
            keep.add(e["name"])
            continue
        age = now - ts
        if age <= timedelta(days=settings.BACKUP_KEEP_ALL_DAYS):
            keep.add(e["name"])
        day, month = ts.date(), (ts.year, ts.month)
        if day not in seen_days and age <= timedelta(days=settings.BACKUP_KEEP_DAILY_DAYS):
            keep.add(e["name"])
        if month not in seen_months and _months_between(now, ts) < settings.BACKUP_KEEP_MONTHLY:
            keep.add(e["name"])
        seen_days.add(day)
        seen_months.add(month)
    return keep


def prune(directory: Optional[Path] = None, now: Optional[datetime] = None) -> List[str]:
    """Delete backups outside the retention policy; returns removed names."""
    d = directory or backup_dir()
    entries = list_backups(d)
    keep = select_keep(entries, now)
    removed = []
    for e in entries:
        if e["name"] in keep:
            continue
        path = d / e["name"]
        for p in (path, _manifest_path(path)):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
        removed.append(e["name"])
    if removed:
        log.info("pruned %d old backup(s) in %s", len(removed), d)
    return removed


# -- status / scheduling -----------------------------------------------------

def status() -> Dict:
    """Backup health summary for the admin page and system status."""
    if not supported():
        return {"supported": False, "enabled": settings.BACKUP_ENABLED}
    entries = list_backups()
    st = _read_json(backup_dir() / _STATUS_FILE) or {}
    good = [e for e in entries if e.get("integrity") == "ok"]
    last = good[0] if good else None
    age = (datetime.now() - last["ts"]).total_seconds() / 3600 if last else None
    mdir = mirror_dir()
    return {
        "supported": True,
        "enabled": settings.BACKUP_ENABLED,
        "dir": str(backup_dir()),
        "mirror_dir": str(mdir) if mdir else None,
        "interval_hours": settings.BACKUP_INTERVAL_HOURS,
        "count": len(entries),
        "total_size": sum(e["size"] for e in entries),
        "last": {k: v for k, v in last.items() if k != "ts"} if last else None,
        "last_age_hours": round(age, 2) if age is not None else None,
        "last_error": st.get("last_error"),
        "last_error_at": st.get("last_error_at"),
        "free_bytes": shutil.disk_usage(backup_dir()).free,
    }


def backup_due(now: Optional[datetime] = None) -> bool:
    """True when the newest regular backup is older than the interval (and a
    failed attempt was not made in the last 30 minutes)."""
    now = now or datetime.now()
    st = _read_json(backup_dir() / _STATUS_FILE) or {}
    if st.get("last_error_at"):
        try:
            if now - datetime.fromisoformat(st["last_error_at"]) < timedelta(minutes=30):
                return False
        except ValueError:
            pass
    regular = [e for e in list_backups() if e["tag"] in ("auto", "manual")
               and e.get("integrity") == "ok"]
    if not regular:
        return True
    return now - regular[0]["ts"] >= timedelta(hours=settings.BACKUP_INTERVAL_HOURS)


def run_maintenance() -> None:
    """Periodic housekeeping that keeps the database fast as it grows."""
    from app.crud import idempotency
    from app.database import SessionLocal, optimize

    try:
        optimize()
    except Exception:  # noqa: BLE001
        log.exception("PRAGMA optimize failed")
    db = SessionLocal()
    try:
        idempotency.purge(db)
    except Exception:  # noqa: BLE001
        log.exception("idempotency-key purge failed")
    finally:
        db.close()


class BackupScheduler:
    """Background thread: takes an automatic backup whenever one is due."""

    def __init__(self, check_every_s: float = 600, first_delay_s: float = 30):
        self.check_every_s = check_every_s
        self.first_delay_s = first_delay_s
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="backup-scheduler",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=10)

    def _run(self) -> None:
        if self._stop.wait(self.first_delay_s):
            return
        while True:
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the scheduler must never die
                log.exception("backup scheduler tick failed")
            if self._stop.wait(self.check_every_s):
                return

    def tick(self) -> None:
        if not backup_due():
            return
        try:
            if create_backup("auto", only_if_due=True) is None:
                return
        except BackupBusy:
            return
        except BackupError:
            pass  # already logged and recorded in the status file
        run_maintenance()


# -- command line --------------------------------------------------------------

def main(argv=None) -> int:
    import argparse

    parser = argparse.ArgumentParser(prog="python -m app.backup",
                                     description="Database backup / restore")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("create", help="take a backup now")
    sub.add_parser("list", help="list backups")
    sub.add_parser("prune", help="apply the retention policy")
    p_verify = sub.add_parser("verify", help="verify a backup")
    p_verify.add_argument("name")
    p_restore = sub.add_parser("restore", help="restore a backup")
    p_restore.add_argument("name")
    p_restore.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    args = parser.parse_args(argv)

    try:
        if args.cmd == "create":
            info = create_backup("manual")
            print(f"created {info['name']}  ({info['size'] / 2**20:.1f} MB, "
                  f"integrity {info['integrity']}, counts {info['counts']})")
        elif args.cmd == "list":
            for e in list_backups():
                print(f"{e['name']:44s} {e['size'] / 2**20:8.1f} MB  "
                      f"{e.get('integrity', '?'):8s} {e.get('counts', '')}")
        elif args.cmd == "prune":
            removed = prune()
            print(f"removed {len(removed)} backup(s)")
        elif args.cmd == "verify":
            r = verify_backup(args.name)
            print(json.dumps(r, ensure_ascii=False, indent=2))
            return 0 if r["ok"] else 1
        elif args.cmd == "restore":
            if not args.yes:
                answer = input(f"Replace the live database with {args.name}? "
                               f"Type 'yes' to continue: ")
                if answer.strip().lower() != "yes":
                    print("aborted")
                    return 1
            r = restore_backup(args.name)
            from app.database import init_db
            init_db()
            print(f"restored {r['restored']} (safety copy of the previous "
                  f"database: {r['pre_restore_backup']})")
    except BackupError as e:
        print(f"error: {e}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
