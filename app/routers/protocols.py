"""Protocol catalogue API."""
from fastapi import APIRouter, HTTPException

from app.iscev import PROTOCOLS, TEST_TYPES, get_protocol

router = APIRouter(prefix="/api/protocols", tags=["protocols"])


@router.get("")
def list_protocols():
    """Protocols grouped by test type (for building the UI)."""
    return TEST_TYPES


@router.get("/all")
def all_protocols():
    return PROTOCOLS


@router.get("/{key}")
def protocol_detail(key: str):
    try:
        return get_protocol(key)
    except KeyError:
        raise HTTPException(404, "Protocol not found")
