"""Driver registry and active-device selection.

Concrete drivers register here under a unique name. The application asks the
registry for the device named by ``settings.ACQUISITION_DRIVER`` so hardware
can be swapped purely through configuration.
"""
from __future__ import annotations

from typing import Dict, List, Type

from app.acquisition.base import AcquisitionDevice
from app.acquisition.simulator import SimulatedDevice
from app.config import settings

_DRIVERS: Dict[str, Type[AcquisitionDevice]] = {}
_ACTIVE: AcquisitionDevice | None = None


def register_driver(name: str, cls: Type[AcquisitionDevice]) -> None:
    _DRIVERS[name] = cls


def list_drivers() -> List[str]:
    return sorted(_DRIVERS)


def get_device(name: str, connection: str = "") -> AcquisitionDevice:
    if name not in _DRIVERS:
        raise KeyError(
            f"Unknown acquisition driver '{name}'. "
            f"Available: {', '.join(list_drivers()) or '(none)'}"
        )
    return _DRIVERS[name](connection=connection)


def get_active_device() -> AcquisitionDevice:
    """Return a singleton instance of the configured driver, connected."""
    global _ACTIVE
    if _ACTIVE is None:
        _ACTIVE = get_device(
            settings.ACQUISITION_DRIVER, settings.DEVICE_CONNECTION
        )
    if not _ACTIVE.is_connected:
        _ACTIVE.connect()
    return _ACTIVE


# Built-in drivers ---------------------------------------------------------
register_driver(SimulatedDevice.name, SimulatedDevice)
