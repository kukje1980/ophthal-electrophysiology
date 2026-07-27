"""Real-time waveform streaming to the browser over a WebSocket.

Streams samples from the selected amplifier driver, marks trigger positions
(for trigger-synchronised averaging on the client) and periodically reports
live electrode impedance.
"""
import asyncio
import math
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.acquisition.streaming import get_live_stream, list_stream_drivers

router = APIRouter(tags=["live"])


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
        "channels": stream.channels, "drivers": list_stream_drivers(),
        "active": stream.name,
        "period_ms": (period / stream.sampling_rate * 1000.0) if period else None,
    })

    total = 0            # samples streamed so far (for trigger alignment)
    last_imp = 0.0
    try:
        while True:
            chunk = stream.read()
            if chunk.size:
                triggers = []
                if period:
                    k = math.ceil(total / period) * period
                    while k < total + chunk.size:
                        triggers.append(int(k - total))
                        k += period
                total += int(chunk.size)
                await ws.send_json({
                    "type": "data",
                    "samples": [round(float(v), 2) for v in chunk],
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
