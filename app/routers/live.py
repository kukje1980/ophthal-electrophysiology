"""Real-time waveform streaming to the browser over a WebSocket.

Streams samples from the selected amplifier driver, marks trigger positions
(for trigger-synchronised averaging on the client) and periodically reports
live electrode impedance.

Robustness: driver calls (open / read / close) run on one dedicated worker
thread, so a slow serial port, DAQ or network device can never stall the
server's event loop (and with it every other user). A heartbeat is sent when
the device is quiet so the browser can tell "no data" from "connection lost",
and driver errors are reported to the browser, which reconnects on its own.
"""
import asyncio
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.acquisition.streaming import get_live_stream, list_stream_drivers

router = APIRouter(tags=["live"])
log = logging.getLogger("app.live")

PUSH_INTERVAL_S = 0.05   # ~20 pushes / second
HEARTBEAT_S = 2.0        # send something at least this often


@router.websocket("/ws/live")
async def live_stream(ws: WebSocket):
    if not ws.session.get("user_id"):
        await ws.close(code=4401)  # unauthenticated
        return
    await ws.accept()

    loop = asyncio.get_running_loop()
    # one thread per connection: many vendor SDKs require every call to come
    # from the thread that opened the device
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="live-stream")

    def call(fn, *args):
        return loop.run_in_executor(executor, fn, *args)

    driver = ws.query_params.get("driver") or None
    connection = ws.query_params.get("connection")
    stream = None
    try:
        try:
            stream = get_live_stream(driver=driver, connection=connection)
            await call(stream.open)
        except Exception as e:  # noqa: BLE001 - report any driver/transport error
            await ws.send_json({"type": "error", "message": f"{type(e).__name__}: {e}",
                                "drivers": list_stream_drivers(), "phase": "open"})
            await ws.close(code=1011)
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
        last_send = time.monotonic()
        while True:
            try:
                chunk = await call(stream.read)
            except Exception as e:  # noqa: BLE001 - device unplugged, transport dropped…
                log.warning("live stream %s read failed: %s", stream.name, e)
                await ws.send_json({"type": "error", "phase": "read",
                                    "message": f"{type(e).__name__}: {e}",
                                    "drivers": list_stream_drivers()})
                await ws.close(code=1011)
                return
            now = time.monotonic()
            if chunk.size:
                triggers = []
                if period:  # periodic trigger (simulator)
                    k = math.ceil(total / period) * period
                    while k < total + chunk.size:
                        triggers.append(int(k - total))
                        k += period
                else:       # event-based triggers detected by the driver
                    triggers = list(getattr(stream, "last_triggers", []))
                total += int(chunk.size)
                await ws.send_json({
                    "type": "data",
                    "samples": [round(float(v), 2) for v in chunk],
                    "triggers": triggers,
                })
                last_send = now
            if now - last_imp >= 1.0:
                imp = await call(stream.impedances)
                if imp is not None:
                    await ws.send_json({"type": "imp", "values": imp})
                    last_send = now
                last_imp = now
            if now - last_send >= HEARTBEAT_S:
                await ws.send_json({"type": "hb"})
                last_send = now
            await asyncio.sleep(PUSH_INTERVAL_S)
    except (WebSocketDisconnect, RuntimeError):
        pass  # browser went away (closed tab, network drop)
    except Exception:  # noqa: BLE001
        log.exception("live stream failed")
    finally:
        if stream is not None:
            try:
                await call(stream.close)
            except Exception:  # noqa: BLE001
                log.exception("closing live stream failed")
        executor.shutdown(wait=False)
