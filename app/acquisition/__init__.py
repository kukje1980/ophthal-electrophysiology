"""Acquisition layer.

This package is the seam between the application and the physical recording
hardware. Everything above this layer talks only to the abstract
``AcquisitionDevice`` contract, so a real device driver can be added later
without touching the routers, models or UI.

To add a real device:
    1. Subclass ``AcquisitionDevice`` (see base.py) and implement the
       connect / configure / acquire_step / disconnect methods using your
       vendor SDK, serial or TCP transport.
    2. Register it:  ``register_driver("my_device", MyDevice)``  (e.g. in this
       package's import side-effects or an entry point).
    3. Select it at runtime with the ``ACQUISITION_DRIVER`` env var.
"""
from app.acquisition.base import AcquiredTrace, AcquisitionDevice, DeviceState
from app.acquisition.registry import (
    get_active_device,
    get_device,
    list_drivers,
    register_driver,
)

__all__ = [
    "AcquiredTrace",
    "AcquisitionDevice",
    "DeviceState",
    "get_active_device",
    "get_device",
    "list_drivers",
    "register_driver",
]
