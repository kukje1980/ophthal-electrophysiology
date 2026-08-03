"""Real transport drivers for the continuous :class:`SampleStream` link.

These register themselves so the live monitor can select them. Transport
libraries are imported lazily inside ``open()`` so the module loads even when a
given library is absent — the error surfaces only when that driver is used.

Coverage:
  * ``lsl``          — Lab Streaming Layer; works with any LSL-capable amp
                       (BioSemi, g.tec, Brain Products, OpenBCI, …). Functional.
  * ``biosemi-tcp``  — BioSemi ActiveTwo / ActiView raw TCP stream. Functional.
  * ``serial-csv``   — generic serial device emitting ASCII sample lines.
                       Functional.
  * ``gtec`` / ``ced`` — vendor-SDK devices; skeletons (SDK required).
"""
from __future__ import annotations

import numpy as np

from app.acquisition.streaming import SampleStream, register_stream


class LSLSampleStream(SampleStream):
    """Pull samples from a Lab Streaming Layer outlet.

    connection: optional LSL stream name to select (else the first stream).
    Requires ``pylsl`` (and the native liblsl); install separately.
    """

    name = "lsl"

    def open(self) -> None:
        from pylsl import StreamInlet, resolve_streams  # lazy

        streams = resolve_streams(wait_time=2.0)
        if not streams:
            raise RuntimeError("No LSL streams found on the network.")
        target = streams[0]
        if self.connection:
            for s in streams:
                if s.name() == self.connection:
                    target = s
                    break
        self._inlet = StreamInlet(target, max_buflen=4)
        info = self._inlet.info()
        if info.nominal_srate():
            self.sampling_rate = float(info.nominal_srate())
        n = info.channel_count()
        self.channels = [f"ch{i + 1}" for i in range(n)]
        self.running = True

    def read(self) -> np.ndarray:
        chunk, _ = self._inlet.pull_chunk(timeout=0.0)
        if not chunk:
            return np.empty(0)
        arr = np.asarray(chunk, dtype=float)
        return arr[:, 0] if arr.ndim == 2 else arr  # channel 0 for display

    def close(self) -> None:
        self._inlet = None
        self.running = False


class BioSemiTcpStream(SampleStream):
    """BioSemi ActiveTwo raw TCP stream (as served by ActiView).

    connection: ``host:port[:nchannels]`` (default 1 channel, 24-bit LE).
    """

    name = "biosemi-tcp"

    def open(self) -> None:
        import socket  # lazy

        parts = self.connection.split(":")
        host = parts[0] or "127.0.0.1"
        port = int(parts[1]) if len(parts) > 1 and parts[1] else 8888
        self._nchan = int(parts[2]) if len(parts) > 2 else 1
        self._sock = socket.create_connection((host, port), timeout=3.0)
        self._sock.setblocking(False)
        self._buf = bytearray()
        self.channels = [f"ch{i + 1}" for i in range(self._nchan)]
        self.running = True

    def read(self) -> np.ndarray:
        try:
            while True:
                data = self._sock.recv(8192)
                if not data:
                    break
                self._buf.extend(data)
        except BlockingIOError:
            pass
        except OSError:
            pass
        frame = self._nchan * 3  # 24-bit samples, channel-interleaved
        n = len(self._buf) // frame
        if n == 0:
            return np.empty(0)
        raw = bytes(self._buf[:n * frame])
        del self._buf[:n * frame]
        out = np.empty(n, dtype=float)
        for s in range(n):  # channel 0 only, 24-bit LE signed -> µV
            b = raw[s * frame: s * frame + 3]
            out[s] = int.from_bytes(b, "little", signed=True) * (2000.0 / (2 ** 23))
        return out

    def close(self) -> None:
        try:
            self._sock.close()
        finally:
            self.running = False


class SerialCsvStream(SampleStream):
    """Generic serial amplifier emitting one ASCII sample (µV) per line.

    connection: ``port[:baud]`` e.g. ``/dev/ttyUSB0:115200``. Requires pyserial.
    """

    name = "serial-csv"

    def open(self) -> None:
        import serial  # lazy

        parts = self.connection.split(":")
        port = parts[0] or "/dev/ttyUSB0"
        baud = int(parts[1]) if len(parts) > 1 and parts[1] else 115200
        self._ser = serial.Serial(port, baud, timeout=0)
        self._buf = b""
        self.running = True

    def read(self) -> np.ndarray:
        data = self._ser.read(8192)
        if data:
            self._buf += data
        vals = []
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            line = line.strip()
            if not line:
                continue
            try:
                vals.append(float(line.split(b",")[0]))
            except ValueError:
                pass
        return np.asarray(vals, dtype=float) if vals else np.empty(0)

    def close(self) -> None:
        try:
            self._ser.close()
        finally:
            self.running = False


def _parse_daq(conn: str):
    """Parse 'Dev1/ai0,Dev1/ai1@2000;gain=10000;trig=Dev1/ai2;thr=1.0'."""
    parts = [p for p in conn.split(";") if p.strip()]
    head = parts[0] if parts else "Dev1/ai0@2000"
    chans, _, rate = head.partition("@")
    channels = [c.strip() for c in chans.split(",") if c.strip()] or ["Dev1/ai0"]
    rate = float(rate) if rate else 2000.0
    opts = {}
    for p in parts[1:]:
        if "=" in p:
            k, v = p.split("=", 1)
            opts[k.strip()] = v.strip()
    return channels, rate, opts


class NiDaqSampleStream(SampleStream):
    """National Instruments DAQ analog input — the digitiser for an analog
    preamplifier such as a Grass (P511 / CP511 / Model 15). Wire the Grass BNC
    outputs to the DAQ analog inputs; optionally feed the stimulator TTL into a
    spare analog input as the trigger.

    connection: ``<sig chans>@<rate>[;gain=G][;trig=<chan>][;thr=<volts>]``
      e.g. ``Dev1/ai0,Dev1/ai1@2000;gain=10000;trig=Dev1/ai7;thr=1.0``

    ``gain`` is the Grass amplifier gain, used to refer samples back to input
    microvolts (µV = DAQ_volts / gain × 1e6). Requires ``nidaqmx`` + NI-DAQmx.
    """

    name = "nidaq"

    def open(self) -> None:
        import nidaqmx  # lazy
        from nidaqmx.constants import AcquisitionType, TerminalConfiguration

        sig, rate, opts = _parse_daq(self.connection)
        self._gain = float(opts.get("gain", 1.0))
        self.sampling_rate = rate
        trig = opts.get("trig")
        self._thr = float(opts.get("thr", 1.0))

        chans = list(sig)
        self._trig_index = None
        if trig:
            self._trig_index = len(chans)
            chans.append(trig)

        self._task = nidaqmx.Task()
        for ch in chans:
            self._task.ai_channels.add_ai_voltage_chan(
                ch, terminal_config=TerminalConfiguration.RSE,
                min_val=-5.0, max_val=5.0)
        self._task.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=int(rate))
        self._nsig = len(sig)
        self.channels = [c.split("/")[-1] for c in sig]  # e.g. ai0, ai1
        self._task.start()
        self.running = True

    def read(self) -> np.ndarray:
        n = self._task.in_stream.avail_samp_per_chan
        if n <= 0:
            self.last_triggers = []
            return np.empty(0)
        data = self._task.read(number_of_samples_per_channel=int(n))
        arr = np.asarray(data, dtype=float)
        if arr.ndim == 1:  # single channel
            sig, trig_row = arr, None
        else:
            sig = arr[0]  # first signal channel (e.g. OD) for display
            trig_row = arr[self._trig_index] if self._trig_index is not None else None
        if trig_row is not None and trig_row.size > 1:
            rising = np.where((trig_row[:-1] < self._thr) &
                              (trig_row[1:] >= self._thr))[0] + 1
            self.last_triggers = [int(i) for i in rising]
        else:
            self.last_triggers = []
        return sig / self._gain * 1e6  # volts -> input-referred µV

    def close(self) -> None:
        try:
            self._task.close()
        finally:
            self.running = False


class GtecStream(SampleStream):
    """g.tec g.USBamp / g.HIamp — via the vendor C/Python API (skeleton)."""

    name = "gtec"

    def open(self) -> None:
        # TODO: import the g.tec API, open the device, set sampling rate /
        # filters, start acquisition; populate self.channels; running = True.
        raise NotImplementedError("Requires the g.tec API / SDK.")

    def read(self) -> np.ndarray:
        raise NotImplementedError("Requires the g.tec API / SDK.")

    def close(self) -> None:
        self.running = False


class CedStream(SampleStream):
    """CED Power1401 / Micro1401 — via the CED SDK (skeleton)."""

    name = "ced"

    def open(self) -> None:
        # TODO: open via the CED SDK, configure ADC + sampling, start.
        raise NotImplementedError("Requires the CED SDK.")

    def read(self) -> np.ndarray:
        raise NotImplementedError("Requires the CED SDK.")

    def close(self) -> None:
        self.running = False


for _cls in (LSLSampleStream, BioSemiTcpStream, SerialCsvStream,
             NiDaqSampleStream, GtecStream, CedStream):
    register_stream(_cls.name, _cls)
