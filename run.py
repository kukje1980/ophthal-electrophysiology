"""Entry point for the Ophthalmic Electrophysiology system.

Usage:
    python run.py                 # production-safe defaults
    RELOAD=1 python run.py        # development: auto-reload on code changes
"""
import uvicorn

from app.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD,
        # close idle keep-alive connections (stale clients on a flaky LAN)
        timeout_keep_alive=30,
        # WebSocket keep-alive: detect dead live-stream connections
        ws_ping_interval=20,
        ws_ping_timeout=20,
        # finish in-flight requests (e.g. a running exam) on shutdown
        timeout_graceful_shutdown=30,
    )
