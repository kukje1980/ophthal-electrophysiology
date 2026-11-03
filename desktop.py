"""Desktop launcher for the packaged (PyInstaller) macOS / Windows builds.

Double-clicking the app:

1. puts the database, photos, backups and logs in a per-user data folder
   (macOS: ~/Library/Application Support/OphthalElectrophysiology,
   Windows: %LOCALAPPDATA%\\OphthalElectrophysiology) and creates a persistent
   random SECRET_KEY there on first start;
2. reads optional overrides from ``settings.env`` in that folder (same names
   as the environment variables in ``app/config.py``);
3. starts the server in a background thread, waits until ``/health`` answers
   and opens the system browser;
4. shows a small control window — closing it stops the server.

It can also be run from a source checkout: ``python desktop.py``.
"""
from __future__ import annotations

import os
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

APP_NAME = "OphthalElectrophysiology"
APP_TITLE = "안과 전기생리검사 (ISCEV ERG / VEP)"
DEFAULT_PORT = 8000


# ---------------------------------------------------------------------------
# Folders
# ---------------------------------------------------------------------------
def resource_dir() -> Path:
    """Folder holding ``static/`` and ``templates/`` (bundle or checkout)."""
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def data_dir() -> Path:
    override = os.environ.get("OEP_DATA_DIR")
    if override:
        return Path(override).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / APP_NAME


_SETTINGS_TEMPLATE = """\
# Ophthal Electrophysiology — 데스크톱 앱 설정
# 이 파일의 값은 환경변수와 같은 이름으로 적용됩니다 (환경변수가 있으면 환경변수가 우선).
# 변경 후 앱을 다시 시작하세요. 사용 가능한 모든 항목은 app/config.py 참조.

# 다른 PC/태블릿에서도 접속하려면 0.0.0.0, 이 컴퓨터에서만 쓰려면 127.0.0.1
#HOST=0.0.0.0
#PORT=8000

# 백업 사본을 둘 두 번째 디스크 / NAS / USB (강력 권장)
#BACKUP_MIRROR_DIR=

# 실제 장비 드라이버 (기본은 시뮬레이터)
#ACQUISITION_DRIVER=simulator
#DEVICE_CONNECTION=sim://localhost
#LIVE_STREAM_DRIVER=sim-stream
#STREAM_CONNECTION=

# 앱 시작 시 브라우저를 자동으로 열지 않으려면 0
#OPEN_BROWSER=1
"""


def load_settings_file(path: Path) -> None:
    """KEY=VALUE lines; environment variables already set take precedence."""
    if not path.exists():
        path.write_text(_SETTINGS_TEMPLATE, encoding="utf-8")
        return
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def ensure_secret_key(path: Path) -> None:
    if os.environ.get("SECRET_KEY"):
        return
    if path.exists():
        key = path.read_text(encoding="utf-8").strip()
    else:
        key = secrets.token_hex(32)
        path.write_text(key, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    os.environ["SECRET_KEY"] = key


def configure_environment() -> Path:
    d = data_dir()
    d.mkdir(parents=True, exist_ok=True)
    load_settings_file(d / "settings.env")
    ensure_secret_key(d / "secret.key")
    posix = d.as_posix()
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{posix}/ophthal_electrophysiology.db")
    os.environ.setdefault("PHOTO_DIR", str(d / "photos"))
    os.environ.setdefault("BACKUP_DIR", str(d / "backups"))
    os.environ.setdefault("LOG_DIR", str(d / "logs"))
    os.environ.setdefault("PORT", str(DEFAULT_PORT))
    os.environ.setdefault("RELOAD", "0")
    # static/ and templates/ are referenced relative to the working directory
    os.chdir(resource_dir())
    return d


def redirect_console(log_dir: Path) -> None:
    """Windowed builds have no console: send prints / tracebacks to a file."""
    if sys.stdout is not None and sys.stderr is not None and not getattr(sys, "frozen", False):
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = open(log_dir / "launcher.log", "a", encoding="utf-8", buffering=1)
        sys.stdout = fh
        sys.stderr = fh
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------
def port_is_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("" if host == "0.0.0.0" else host, port))
            return True
        except OSError:
            return False


def health_ok(port: int, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=timeout) as r:
            return r.status == 200 and b'"status":"ok"' in r.read().replace(b" ", b"")
    except Exception:  # noqa: BLE001
        return False


def pick_port(host: str, wanted: int) -> int:
    if port_is_free(host, wanted):
        return wanted
    for p in range(wanted + 1, wanted + 20):
        if port_is_free(host, p):
            return p
    raise RuntimeError(f"포트 {wanted}~{wanted + 19} 를 모두 사용 중입니다")


class ServerThread(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(name="uvicorn", daemon=True)
        self.host, self.port = host, port
        self.error: BaseException | None = None
        self._server = None

    def run(self):
        try:
            import uvicorn
            from app.main import app  # heavy import: FastAPI, SQLAlchemy, numpy

            config = uvicorn.Config(
                app, host=self.host, port=self.port, log_level="info",
                timeout_keep_alive=30, ws_ping_interval=20, ws_ping_timeout=20,
                timeout_graceful_shutdown=30,
            )
            self._server = uvicorn.Server(config)
            self._server.run()
        except BaseException as e:  # noqa: BLE001
            self.error = e
            traceback.print_exc()

    def stop(self):
        if self._server is not None:
            self._server.should_exit = True


def wait_until_ready(server: ServerThread, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if server.error is not None or not server.is_alive():
            return False
        if health_ok(server.port):
            return True
        time.sleep(0.25)
    return False


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
def control_window(url: str, server: ServerThread, data: Path) -> bool:
    """Tiny Tk window with Open / Quit. Returns False if Tk is unavailable."""
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:  # noqa: BLE001
        return False

    root = tk.Tk()
    root.title(APP_TITLE)
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
        root.after(1500, lambda: root.attributes("-topmost", False))
    except tk.TclError:
        pass

    frame = ttk.Frame(root, padding=18)
    frame.grid(sticky="nsew")
    ttk.Label(frame, text=APP_TITLE, font=("TkDefaultFont", 13, "bold")).grid(
        row=0, column=0, columnspan=2, sticky="w")
    status = tk.StringVar(value=f"서버 실행 중 — {url}")
    ttk.Label(frame, textvariable=status).grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Label(frame, text=f"데이터 폴더: {data}", foreground="#666").grid(
        row=2, column=0, columnspan=2, sticky="w", pady=(2, 12))
    ttk.Label(frame, text="이 창을 닫으면 서버가 종료되고 접속이 끊어집니다.",
              foreground="#a33").grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 12))

    def open_browser():
        webbrowser.open(url)

    def open_folder():
        if sys.platform == "darwin":
            os.system(f'open "{data}"')
        elif os.name == "nt":
            os.startfile(str(data))  # type: ignore[attr-defined]
        else:
            os.system(f'xdg-open "{data}"')

    def quit_app():
        status.set("서버를 종료하는 중…")
        root.update_idletasks()
        server.stop()
        server.join(timeout=35)
        root.destroy()

    ttk.Button(frame, text="브라우저 열기", command=open_browser).grid(row=4, column=0, sticky="ew", padx=(0, 6))
    ttk.Button(frame, text="데이터 폴더", command=open_folder).grid(row=4, column=1, sticky="ew")
    ttk.Button(frame, text="종료", command=quit_app).grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 0))
    root.protocol("WM_DELETE_WINDOW", quit_app)
    try:
        root.createcommand("::tk::mac::Quit", quit_app)  # Cmd+Q on macOS
    except tk.TclError:
        pass

    def watchdog():
        if not server.is_alive():
            status.set("서버가 중지되었습니다. logs/launcher.log 를 확인하세요.")
        else:
            root.after(2000, watchdog)

    root.after(2000, watchdog)
    root.mainloop()
    return True


def show_error(title: str, message: str) -> None:
    print(f"{title}: {message}")
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(title, message)
        root.destroy()
    except Exception:  # noqa: BLE001
        pass


# ---------------------------------------------------------------------------
def main() -> int:
    data = configure_environment()
    redirect_console(Path(os.environ["LOG_DIR"]))
    host = os.environ.get("HOST", "0.0.0.0")
    wanted = int(os.environ["PORT"])

    # Already running (second double-click)? Just bring the browser up.
    if not port_is_free(host, wanted) and health_ok(wanted):
        webbrowser.open(f"http://localhost:{wanted}/")
        return 0

    try:
        port = pick_port(host, wanted)
    except RuntimeError as e:
        show_error(APP_TITLE, str(e))
        return 1
    url = f"http://localhost:{port}/"

    server = ServerThread(host, port)
    server.start()
    if not wait_until_ready(server):
        detail = f"{type(server.error).__name__}: {server.error}" if server.error else "시간 초과"
        show_error(APP_TITLE, f"서버를 시작할 수 없습니다.\n{detail}\n\n로그: {data / 'logs'}")
        return 1

    if os.environ.get("OPEN_BROWSER", "1") == "1":
        webbrowser.open(url)
    print(f"[desktop] {APP_TITLE} ready at {url} (data: {data})")

    if not control_window(url, server, data):
        # No Tk: behave like a console server until Ctrl+C / window close.
        try:
            while server.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            server.stop()
            server.join(timeout=35)
    return 0


if __name__ == "__main__":
    sys.exit(main())
