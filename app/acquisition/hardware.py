"""Skeleton driver for a real amplifier + stimulator.

This is a *template*, not a working driver. Copy it, fill in the transport
(serial / TCP-SCPI / vendor SDK) for your hardware, then register the device:

    from app.acquisition import register_driver
    from app.acquisition.hardware import HardwareDevice
    register_driver("my_lab_rig", HardwareDevice)

and select it at runtime without touching any other code:

    export ACQUISITION_DRIVER=my_lab_rig
    export DEVICE_CONNECTION="amp=/dev/ttyUSB0;stim=192.168.0.10:5025"

The connection string format is up to you; parse it in ``__init__``. Each
method below marks exactly where the vendor calls belong. The averaging,
artifact-rejection and trigger sequencing are already handled by
:class:`~app.acquisition.base.CompositeDevice`.
"""
from __future__ import annotations

import numpy as np

from app.acquisition.amplifier import (
    Amplifier,
    AmplifierState,
    ImpedanceReport,
)
from app.acquisition.base import CompositeDevice
from app.acquisition.stimulator import (
    Stimulator,
    StimulatorState,
    StimulusCommand,
    TriggerEvent,
)


class HardwareStimulator(Stimulator):
    """Real visual stimulator (Ganzfeld / pattern display)."""

    name = "hardware-stimulator"

    def connect(self) -> None:
        # TODO: open serial/TCP link; verify identity; self.state = READY
        raise NotImplementedError("Implement stimulator transport (connect).")

    def disconnect(self) -> None:
        # TODO: close link; self.state = DISCONNECTED
        raise NotImplementedError("Implement stimulator transport (disconnect).")

    def load(self, command: StimulusCommand) -> None:
        super().load(command)
        # TODO: program intensity / background / pattern / rate from `command`
        raise NotImplementedError("Send the stimulus parameters to the device.")

    def present(self, sweep_index: int = 0) -> TriggerEvent:
        # TODO: present one stimulus and raise the hardware (TTL) trigger
        raise NotImplementedError("Present stimulus and emit the trigger pulse.")


class HardwareAmplifier(Amplifier):
    """Real biopotential amplifier."""

    name = "hardware-amplifier"

    def connect(self) -> None:
        # TODO: open serial/TCP link; verify identity; self.state = READY
        raise NotImplementedError("Implement amplifier transport (connect).")

    def disconnect(self) -> None:
        # TODO: close link; self.state = DISCONNECTED
        raise NotImplementedError("Implement amplifier transport (disconnect).")

    def configure(self, settings) -> None:
        super().configure(settings)
        # TODO: program gain, high-pass/low-pass/notch filters and sampling
        raise NotImplementedError("Send the acquisition settings to the device.")

    def check_impedance(self, limit_kohm: float = 5.0) -> ImpedanceReport:
        # TODO: run the device's electrode-impedance test, return per-channel kΩ
        raise NotImplementedError("Query per-electrode impedance.")

    def arm(self) -> None:
        # TODO: put the amplifier in armed/wait-for-trigger mode
        raise NotImplementedError("Arm the amplifier for the next trigger.")

    def capture_sweep(self, stimulus: StimulusCommand, eye: str) -> np.ndarray:
        # TODO: block until the trigger fires, then read back one sweep
        # (microvolts, settings.n_samples() long). Ignore `stimulus`/`eye`.
        raise NotImplementedError("Read one triggered sweep from the device.")


class HardwareDevice(CompositeDevice):
    """A real rig = HardwareAmplifier + HardwareStimulator.

    Override ``__init__`` to parse ``connection`` into separate amplifier and
    stimulator endpoints for your hardware.
    """

    name = "hardware"

    def __init__(self, connection: str = ""):
        super().__init__(
            amplifier=HardwareAmplifier(connection),
            stimulator=HardwareStimulator(connection),
            connection=connection,
        )


# ---------------------------------------------------------------------------
# Real-time streaming transport skeletons
#
# These implement the continuous SampleStream contract (see
# app.acquisition.streaming). Fill in the transport read loop for your device;
# the host side (ring buffer, trigger epoching, averaging, live view) is
# already provided.
# ---------------------------------------------------------------------------
import numpy as np  # noqa: E402

from app.acquisition.streaming import SampleStream  # noqa: E402


class SerialSampleStream(SampleStream):
    """Continuous samples over a serial / USB-CDC link (e.g. /dev/ttyUSB0)."""

    name = "serial-stream"

    def open(self) -> None:
        # TODO: import serial; self._port = serial.Serial(self.connection,
        #       baudrate=..., timeout=0)  then start streaming; running = True
        raise NotImplementedError("Open the serial port and start streaming.")

    def read(self) -> np.ndarray:
        # TODO: read whatever bytes are available, parse the device's frame
        # format into microvolt samples, and return them as a 1-D float array.
        raise NotImplementedError("Read + parse the serial sample frames.")

    def close(self) -> None:
        # TODO: self._port.close(); running = False
        raise NotImplementedError("Close the serial port.")


class TcpSampleStream(SampleStream):
    """Continuous samples over a TCP socket (e.g. 192.168.0.10:5025)."""

    name = "tcp-stream"

    def open(self) -> None:
        # TODO: host, port = self.connection.split(":"); open socket,
        #       send the start-streaming command; running = True
        raise NotImplementedError("Connect the socket and start streaming.")

    def read(self) -> np.ndarray:
        # TODO: recv available bytes, de-frame the binary sample blocks into
        # a microvolt float array (mind endianness and partial frames).
        raise NotImplementedError("Receive + de-frame the TCP sample blocks.")

    def close(self) -> None:
        # TODO: send stop command; close the socket; running = False
        raise NotImplementedError("Close the socket.")
