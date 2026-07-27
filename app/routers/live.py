"""Real-time waveform streaming to the browser over a WebSocket.

Demonstrates the continuous amplifier link: a background sample stream is
polled and pushed to the client as it arrives, so the page shows a live,
scrolling trace exactly as it would from a real recorder.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.acquisition.streaming import get_live_stream

router = APIRouter(tags=["live"])


@router.websocket("/ws/live")
async def live_stream(ws: WebSocket):
    # WebSockets bypass the HTTP auth gate, so authenticate from the session.
    if not ws.session.get("user_id"):
        await ws.close(code=4401)  # unauthenticated
        return

    await ws.accept()
    stream = get_live_stream(sampling_rate=1000.0)
    stream.open()
    await ws.send_json({"type": "meta", "fs": stream.sampling_rate,
                        "device": stream.name})
    try:
        while True:
            chunk = stream.read()
            if chunk.size:
                await ws.send_json({
                    "type": "data",
                    "samples": [round(float(v), 2) for v in chunk],
                })
            await asyncio.sleep(0.05)  # ~20 pushes/second
    except WebSocketDisconnect:
        pass
    finally:
        stream.close()
