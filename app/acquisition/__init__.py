"""Acquisition layer.

This package is the seam between the application and the physical recording
hardware. Everything above this layer talks only to the abstract
``AcquisitionDevice`` contract, so a real device driver can be added later
without touching the routers, models or UI.

A real system is two instruments - a biopotential ``Amplifier`` and a visual
``Stimulator`` - linked by a trigger line. ``CompositeDevice`` pairs them and
implements the trigger-synchronised averaging loop, so a real device only
needs the two drivers.

To add a real device:
    1. Implement an ``Amplifier`` (gain / filters / sampling / impedance /
       triggered capture) and a ``Stimulator`` (stimulus + trigger). See
       ``hardware.py`` for a ready-to-fill skeleton.
    2. Pair them in a ``CompositeDevice`` subclass and register it:
       ``register_driver("my_device", MyDevice)``.
    3. Select it at runtime with the ``ACQUISITION_DRIVER`` env var.
"""
from app.acquisition.amplifier import (
    Amplifier,
    AmplifierSettings,
    AmplifierState,
    ImpedanceReport,
)
from app.acquisition.base import (
    AcquiredTrace,
    AcquisitionDevice,
    CompositeDevice,
    DeviceState,
)
from app.acquisition.registry import (
    get_active_device,
    get_device,
    list_drivers,
    register_driver,
)
from app.acquisition.stimulator import (
    Stimulator,
    StimulatorState,
    StimulusCommand,
    TriggerEvent,
)
from app.acquisition.streaming import (
    SampleStream,
    SimulatedStream,
    get_live_stream,
    get_stream,
    list_stream_drivers,
    register_stream,
)

__all__ = [
    "AcquiredTrace",
    "AcquisitionDevice",
    "CompositeDevice",
    "DeviceState",
    "Amplifier",
    "AmplifierSettings",
    "AmplifierState",
    "ImpedanceReport",
    "Stimulator",
    "StimulatorState",
    "StimulusCommand",
    "TriggerEvent",
    "SampleStream",
    "SimulatedStream",
    "get_live_stream",
    "get_stream",
    "list_stream_drivers",
    "register_stream",
    "get_active_device",
    "get_device",
    "list_drivers",
    "register_driver",
]
