"""Application logging: console plus a size-rotated log file.

Rotation keeps the log bounded (10 × 10 MB by default) so a server that runs
for years never fills its disk with logs.
"""
import logging
import logging.handlers
from pathlib import Path

from app.config import settings

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"
_configured = False


def setup_logging(max_bytes: int = 10 * 1024 * 1024, backups: int = 10) -> None:
    global _configured
    if _configured:
        return
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
    app_log = logging.getLogger("app")
    app_log.setLevel(level)

    handlers = []
    try:
        log_dir = Path(settings.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_dir / "app.log", maxBytes=max_bytes, backupCount=backups,
            encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FORMAT))
        handlers.append(fh)
    except OSError as e:  # unwritable log dir must not stop the server
        logging.getLogger(__name__).warning("file logging disabled: %s", e)
    if not any(isinstance(h, logging.StreamHandler) for h in logging.getLogger().handlers):
        sh = logging.StreamHandler()
        sh.setFormatter(logging.Formatter(_FORMAT))
        app_log.addHandler(sh)
    for h in handlers:
        app_log.addHandler(h)
        # server errors (tracebacks of failed requests) go to the same file
        logging.getLogger("uvicorn.error").addHandler(h)
    _configured = True
