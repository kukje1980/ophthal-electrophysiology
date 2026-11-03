"""Launcher for the packaged (PyInstaller) build.

Runs the server from the folder the executable lives in, so the database,
photos, backups and logs are created next to it, then opens the browser.

    OphthalElectrophysiology.exe              # start and open the browser
    OphthalElectrophysiology.exe --no-browser # start only (e.g. as a service)

Settings are read from environment variables (see README, "Configuration").
For the packaged build they can also be written to a ``settings.env`` file
next to the executable, one ``KEY=VALUE`` per line.
"""
import multiprocessing
import os
import sys
import threading
import webbrowser


def _base_dir() -> str:
    if getattr(sys, "frozen", False):          # PyInstaller bundle
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env_file(path: str) -> None:
    """Apply KEY=VALUE lines from *path*; existing variables win."""
    if not os.path.isfile(path):
        return
    with open(path, encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def main() -> None:
    base = _base_dir()
    os.chdir(base)
    _load_env_file(os.path.join(base, "settings.env"))
    os.environ.setdefault("RELOAD", "0")
    if not getattr(sys, "frozen", False):
        sys.path.insert(0, base)

    import uvicorn

    from app import __version__
    from app.config import settings
    from app.main import app

    url = f"http://localhost:{settings.PORT}"
    print(f"안과 전기생리 검사 시스템 v{__version__}")
    print(f"데이터 폴더: {base}")
    print(f"브라우저 주소: {url}  (이 창을 닫으면 서버가 종료됩니다)")
    if "--no-browser" not in sys.argv[1:]:
        threading.Timer(1.5, webbrowser.open, [url]).start()

    uvicorn.run(
        app,
        host=settings.HOST,
        port=settings.PORT,
        timeout_keep_alive=30,
        ws_ping_interval=20,
        ws_ping_timeout=20,
        timeout_graceful_shutdown=30,
    )


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
