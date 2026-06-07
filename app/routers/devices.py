"""Acquisition device API.

Exposes the driver registry and the active device so the front-end (and any
integrator) can see and control the hardware connection.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.acquisition import get_active_device, get_device, list_drivers

router = APIRouter(prefix="/api/devices", tags=["devices"])


class ConnectRequest(BaseModel):
    driver: str
    connection: str = ""


@router.get("")
def list_devices():
    """All registered drivers plus the currently active device's status."""
    return {
        "drivers": list_drivers(),
        "active": get_active_device().status(),
    }


@router.get("/status")
def device_status():
    return get_active_device().status()


@router.post("/connect")
def connect_device(req: ConnectRequest):
    """Instantiate and connect a driver (validates a connection works)."""
    try:
        dev = get_device(req.driver, req.connection)
    except KeyError as e:
        raise HTTPException(404, str(e))
    try:
        dev.connect()
    except Exception as e:  # noqa: BLE001 - surface any driver error
        raise HTTPException(503, f"Connect failed: {e}")
    return dev.status()
