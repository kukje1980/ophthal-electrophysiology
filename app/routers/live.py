"""Real-time waveform streaming to the browser over a WebSocket.

Streams samples from the selected amplifier driver (one row per signal
channel, e.g. OD and OS), marks trigger positions (for trigger-synchronised
averaging on the client) and periodically reports live electrode impedance.
"""
import asyncio
import math
import time

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.acquisition.hw_streams import discover_nidaq
from app.acquisition.streaming import get_live_stream, list_stream_drivers

router = APIRouter(tags=["live"])


@router.get("/api/live/daq")
def daq_devices():
    """NI-DAQmx devices attached to this PC, for the connection builder."""
    return discover_nidaq()


@router.websocket("/ws/live")
async def live_stream(ws: WebSocket):
    if not ws.session.get("user_id"):
        await ws.close(code=4401)  # unauthenticated
        return
    await ws.accept()

    driver = ws.query_params.get("driver") or None
    connection = ws.query_params.get("connection")
    try:
        stream = get_live_stream(driver=driver, connection=connection)
        stream.open()
    except Exception as e:  # noqa: BLE001 - report any driver/transport error
        await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}",
                            "drivers": list_stream_drivers()})
        await ws.close()
        return

    period = stream.trigger_period_samples
    await ws.send_json({
        "type": "meta", "fs": stream.sampling_rate, "device": stream.name,
        "channels": stream.channels, "signals": stream.signals,
        "drivers": list_stream_drivers(),
        "active": stream.name,
        "period_ms": (period / stream.sampling_rate * 1000.0) if period else None,
    })

    total = 0            # samples streamed so far (for trigger alignment)
    last_imp = 0.0
    try:
        while True:
            chunk = np.atleast_2d(stream.read())  # (signals, n)
            n = chunk.shape[1]
            if n:
                triggers = []
                if period:  # periodic trigger (simulator)
                    k = math.ceil(total / period) * period
                    while k < total + n:
                        triggers.append(int(k - total))
                        k += period
                else:       # event-based triggers detected by the driver
                    triggers = list(getattr(stream, "last_triggers", []))
                total += n
                await ws.send_json({
                    "type": "data",
                    "samples": [[round(float(v), 2) for v in row] for row in chunk],
                    "triggers": triggers,
                })
            now = time.time()
            if now - last_imp >= 1.0:
                imp = stream.impedances()
                if imp is not None:
                    await ws.send_json({"type": "imp", "values": imp})
                last_imp = now
            await asyncio.sleep(0.05)  # ~20 pushes/second
    except WebSocketDisconnect:
        pass
    finally:
        stream.close()
