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
  * ``nidaq``        — NI-DAQmx analog input for an analog preamplifier
                       (OD/OS channels + trigger line). Functional;
                       :func:`discover_nidaq` lists the attached devices.
  * ``gtec`` / ``ced`` — vendor-SDK devices; skeletons (SDK required).
"""
from __future__ import annotations

import numpy as np

from app.acquisition.streaming import SampleStream, register_stream, split_options


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
    head, opts = split_options(conn)
    chans, _, rate = (head or "Dev1/ai0@2000").partition("@")
    channels = [c.strip() for c in chans.split(",") if c.strip()] or ["Dev1/ai0"]
    rate = float(rate) if rate else 2000.0
    return channels, rate, opts


class NiDaqSampleStream(SampleStream):
    """National Instruments DAQ analog input — the digitiser for an analog
    preamplifier such as a Grass (P511 / CP511 / Model 15). Wire the Grass BNC
    outputs to the DAQ analog inputs (first = OD, second = OS); optionally
    feed the stimulator TTL into a spare analog input as the trigger.

    connection: ``<sig chans>@<rate>[;gain=G[,G2]][;trig=<chan>][;thr=<volts>]``
                ``[;edge=rise|fall][;eyes=OD,OS][;range=<volts>]``
                ``[;diff=1][;notch=60][;hp=0.3]``
      e.g. ``Dev1/ai0,Dev1/ai1@2000;gain=10000;trig=Dev1/ai7;thr=1.0;diff=1;notch=60``

    ``gain`` is the Grass amplifier gain — one value for all channels or one
    per channel — used to refer samples back to input microvolts
    (µV = DAQ_volts / gain × 1e6). ``eyes`` labels the signal channels
    (default OD, OS). ``range`` is the DAQ input range in volts (default ±5).
    ``edge=fall`` detects an active-low trigger. ``diff=1`` selects
    differential signal inputs (common-mode noise rejection; wire +/- pairs;
    the trigger stays single-ended).
    ``notch`` adds a stateful mains notch (Hz) and ``hp`` a DC-blocking
    high-pass (Hz) to each channel. Requires ``nidaqmx`` + NI-DAQmx.
    """

    name = "nidaq"

    def open(self) -> None:
        import nidaqmx  # lazy
        from nidaqmx.constants import AcquisitionType, TerminalConfiguration

        from app.acquisition.filters import DCBlock, FilterChain, Notch

        sig, rate, opts = _parse_daq(self.connection)
        gains = [float(g) for g in opts.get("gain", "1").split(",") if g.strip()]
        if len(gains) == 1:
            gains *= len(sig)
        if len(gains) != len(sig):
            raise ValueError("gain= needs one value or one per signal channel")
        self._gain = np.asarray(gains, dtype=float)[:, None]
        self.sampling_rate = rate
        trig = opts.get("trig")
        self._thr = float(opts.get("thr", 1.0))
        self._falling = opts.get("edge") == "fall"
        self._last_trig_v = None
        vmax = float(opts.get("range", 5.0))
        term = (TerminalConfiguration.DIFF if opts.get("diff") in ("1", "true")
                else TerminalConfiguration.RSE)
        notch = float(opts["notch"]) if opts.get("notch") else None
        hp = float(opts["hp"]) if opts.get("hp") else None
        # filters are stateful, so each channel gets its own chain
        self._filters = [FilterChain(
            DCBlock(rate, hp) if hp else None,
            Notch(rate, notch) if notch else None,
        ) for _ in sig]

        labels = [e.strip() for e in opts.get("eyes", "").split(",") if e.strip()]
        default = ["OD", "OS"]
        self.signals = [labels[i] if i < len(labels)
                        else default[i] if i < len(default) else f"ch{i + 1}"
                        for i in range(len(sig))]

        self._task = nidaqmx.Task()
        for ch in sig:
            self._task.ai_channels.add_ai_voltage_chan(
                ch, terminal_config=term, min_val=-vmax, max_val=vmax)
        self._trig_index = None
        if trig:  # a TTL is ground-referenced (single-ended) and up to 5 V
            self._trig_index = len(sig)
            tmax = max(vmax, 5.0)
            self._task.ai_channels.add_ai_voltage_chan(
                trig, terminal_config=TerminalConfiguration.RSE,
                min_val=-tmax, max_val=tmax)
        self._task.timing.cfg_samp_clk_timing(
            rate, sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=int(rate))
        self._nsig = len(sig)
        self.channels = [c.split("/")[-1] for c in sig]  # e.g. ai0, ai1
        self._task.start()
        self.running = True

    def _edges(self, trig_row: np.ndarray) -> list:
        """Trigger edges in this chunk, including one that falls between the
        previous chunk's last sample and this chunk's first."""
        prev = np.empty_like(trig_row)
        prev[0] = trig_row[0] if self._last_trig_v is None else self._last_trig_v
        prev[1:] = trig_row[:-1]
        self._last_trig_v = float(trig_row[-1])
        if self._falling:
            hit = (prev > self._thr) & (trig_row <= self._thr)
        else:
            hit = (prev < self._thr) & (trig_row >= self._thr)
        return [int(i) for i in np.where(hit)[0]]

    def read(self) -> np.ndarray:
        n = self._task.in_stream.avail_samp_per_chan
        if n <= 0:
            self.last_triggers = []
            return np.empty((self._nsig, 0))
        data = self._task.read(number_of_samples_per_channel=int(n))
        arr = np.atleast_2d(np.asarray(data, dtype=float))  # (channels, n)
        sig = arr[:self._nsig]
        if self._trig_index is not None and arr.shape[1]:
            self.last_triggers = self._edges(arr[self._trig_index])
        else:
            self.last_triggers = []
        uv = sig / self._gain * 1e6  # volts -> input µV
        return np.vstack([f.process(row) for f, row in zip(self._filters, uv)])

    def close(self) -> None:
        try:
            self._task.close()
        finally:
            self.running = False


def discover_nidaq() -> dict:
    """List the NI-DAQmx devices attached to this PC (for the connection
    builder on the Live page). Never raises: when the ``nidaqmx`` package or
    the NI-DAQmx runtime is missing, ``available`` is False with a reason."""
    try:
        import nidaqmx.system  # lazy
    except ImportError:
        return {"available": False, "devices": [],
                "reason": "nidaqmx 패키지가 없습니다 — pip install nidaqmx 후 "
                          "ni.com의 NI-DAQmx 드라이버(런타임)를 설치하세요."}
    try:
        system = nidaqmx.system.System.local()
        devices = [_describe_nidaq(d) for d in system.devices]
    except Exception as e:  # noqa: BLE001 - runtime missing / driver error
        return {"available": False, "devices": [],
                "reason": f"NI-DAQmx 드라이버(런타임)에 접근할 수 없습니다: "
                          f"{type(e).__name__}: {e}"}
    try:
        v = system.driver_version
        version = f"{v.major_version}.{v.minor_version}.{v.update_version}"
    except Exception:  # noqa: BLE001
        version = None
    return {"available": True, "driver_version": version, "devices": devices}


def _describe_nidaq(dev) -> dict:
    def attr(name, default=None):
        try:
            return getattr(dev, name)
        except Exception:  # noqa: BLE001 - property unsupported on this model
            return default

    serial = attr("dev_serial_num")
    rngs = list(attr("ai_voltage_rngs") or [])
    return {
        "name": dev.name,
        "product_type": attr("product_type", ""),
        "serial": f"{serial:X}" if isinstance(serial, int) else serial,
        "simulated": bool(attr("dev_is_simulated", False)),
        "ai_channels": [c.name for c in (attr("ai_physical_chans") or [])],
        "ai_max_single_rate": attr("ai_max_single_chan_rate"),
        "ai_max_multi_rate": attr("ai_max_multi_chan_rate"),
        "ai_ranges_v": [rngs[i:i + 2] for i in range(0, len(rngs) - 1, 2)],
    }


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
