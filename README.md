# Ophthalmic Electrophysiology (ISCEV ERG / VEP)

A FastAPI + web application for recording, analysing and reporting clinical
visual electrophysiology studies following the current **ISCEV** standards:

| Test  | ISCEV standard | Protocols |
|-------|----------------|-----------|
| **ffERG** | ffERG 2022 | DA 0.01, DA 3, DA 10, dark-adapted oscillatory potentials (75–300 Hz), LA 3 (30 cd·m⁻² background), LA 30 Hz flicker |
| **PERG**  | PERG 2024 | transient pattern ERG — 0.8° checks, 15°×15° field, 98% contrast (N35 / P50 / N95) |
| **VEP**   | VEP 2025 | pattern-reversal 1.0°(60′)/0.25°(15′) checks at 2 rev/s (N75 / P100 / **N145**), flash VEP (≥20° field) |
| **mfERG** | mfERG 2021 | light-adapted 61- and 103-hexagon arrays over 40–50° (N1 / P1 / N2) |

> The pattern-reversal third component follows the **2025 VEP standard**, which
> renamed **N135 → N145**.

It acquires waveforms, **auto-detects the standard markers** (a/b-wave,
oscillatory potentials, P50, N95, P100, …), measures implicit time and
amplitude, classifies them against reference ranges, and renders printable
reports.

## Quick start

```bash
pip install -r requirements.txt
python run.py
```

Open <http://localhost:8000>. Interactive API docs at `/docs`.

Typical flow: **Patients → add patient → New exam → pick protocol → Acquire →
Report**.

## Architecture

```
app/
  main.py            FastAPI app
  config.py          settings (env-overridable)
  database.py        SQLAlchemy engine/session
  models/            Patient, Exam, Waveform, Measurement
  schemas/           Pydantic I/O
  crud/              DB access + acquire→store→auto-mark pipeline
  routers/           patients, exams, protocols, devices, pages (HTML)
  iscev/             protocol catalogue, reference ranges, marker detection
  acquisition/       device abstraction (the hardware seam)
    amplifier.py     biopotential amplifier contract
    stimulator.py    visual stimulator contract
    base.py          AcquisitionDevice + CompositeDevice (averaging loop)
    simulator.py     simulated amplifier + stimulator (default driver)
    hardware.py      ready-to-fill skeleton for a real rig
    registry.py      driver registry + active-device selection
templates/  static/  Jinja2 pages + Canvas plotting
```

## Real-device integration (amplifier + stimulator)

A clinical electrophysiology system is **two instruments linked by a trigger
line**: a biopotential **amplifier** (gain, band-pass / notch filters,
sampling, electrode-impedance check, triggered capture) and a visual
**stimulator** (Ganzfeld flash / background / flicker, or pattern / multifocal
display, plus the trigger pulse). The application models them as two separate
contracts:

| Contract | File | Responsibility |
|----------|------|----------------|
| `Amplifier` | `app/acquisition/amplifier.py` | `connect` · `configure(AmplifierSettings)` · `check_impedance` · `arm` · `capture_sweep` |
| `Stimulator` | `app/acquisition/stimulator.py` | `connect` · `load(StimulusCommand)` · `present` (emit stimulus + trigger) |

`CompositeDevice` (in `base.py`) pairs an amplifier with a stimulator and
implements the shared **trigger-synchronised averaging loop** once:

```
configure amplifier + load stimulus → impedance check → for each sweep:
  amplifier.arm() → stimulator.present() (raises trigger) →
  amplifier.capture_sweep() → reject artifacts → average → AcquiredTrace
```

It also maps every ISCEV protocol step to concrete amplifier settings and a
stimulus command (filters, gain, sweeps-to-average and artifact threshold per
step kind — e.g. OPs 75–300 Hz, PERG ×100 sweeps, VEP ×64). The built-in
`simulator` driver is a `CompositeDevice` of a `SimulatedAmplifier` +
`SimulatedStimulator`, so the full pipeline runs without hardware.

To plug in a **real recorder**, fill in the skeleton in
`app/acquisition/hardware.py`:

1. **Implement the two drivers** — subclass `Amplifier` and `Stimulator`,
   adding your vendor SDK / serial / TCP-SCPI transport at the marked `TODO`s.
   Pair them in a `CompositeDevice` subclass (see `HardwareDevice`).

2. **Register it**:

   ```python
   from app.acquisition import register_driver
   from app.acquisition.hardware import HardwareDevice
   register_driver("my_rig", HardwareDevice)
   ```

3. **Select it** via environment variables — no other code changes:

   ```bash
   export ACQUISITION_DRIVER=my_rig
   export DEVICE_CONNECTION="amp=/dev/ttyUSB0;stim=192.168.0.10:5025"
   python run.py
   ```

The `/api/devices` endpoints expose the registry and live device status
(including the amplifier, stimulator and last impedance check), and
`crud.run_exam` drives whichever driver is active. Everything above the
acquisition layer (models, analysis, UI, reports) is unchanged whether the
data comes from the simulator or real hardware.

### Real-time streaming (the continuous amplifier link)

The sweep contract models *averaged* acquisition; real recorders also stream
samples continuously. `app/acquisition/streaming.py` defines the `SampleStream`
contract (`open` / `read` / `close`, optional `impedances()`) for that
continuous link, with a registry of drivers selectable at runtime
(`LIVE_STREAM_DRIVER` / `STREAM_CONNECTION`):

| Driver | Status | Transport |
|--------|--------|-----------|
| `sim-stream` | built-in | wall-clock-paced two-eye (OD/OS) ERG signal (no hardware); `;hum=<µV>`, `;blink=1`, `;cal=<µV>` simulate mains hum, blinks and a CAL pulse |
| `lsl` | functional | Lab Streaming Layer — BioSemi / g.tec / Brain Products / OpenBCI (needs `pylsl`) |
| `biosemi-tcp` | functional | BioSemi ActiveTwo raw TCP stream |
| `serial-csv` | functional | generic serial ASCII samples (needs `pyserial`) |
| `nidaq` | functional | NI-DAQmx analog input — digitiser for an **analog preamplifier (e.g. Grass P511 / CP511 / Model 15)**; OD + OS channels, optional trigger channel, gain→µV (needs `nidaqmx`) |
| `gtec` / `ced` | skeleton | vendor SDK required |

**Analog preamplifier (Grass, etc.) via a DAQ:** wire the amplifier's BNC
outputs to the DAQ analog inputs (ch0 = OD, ch1 = OS) and, optionally, the
stimulator TTL into a spare input as the trigger. Select the `nidaq` driver
with e.g. `Dev1/ai0,Dev1/ai1@2000;gain=10000;trig=Dev1/ai7;thr=1.0`
(`gain` = the preamp gain, used to refer samples back to input µV; one value
or one per channel, e.g. `gain=10000,20000`). Both channels are streamed and
averaged together, so both eyes are recorded at once. Add `;diff=1` for
differential signal inputs (common-mode rejection; the trigger stays
single-ended), `;notch=60` for a stateful mains notch and `;hp=0.3` for
DC/baseline removal (`app/acquisition/filters.py`); `;range=<V>` sets the DAQ
input range (default ±5 V), `;edge=fall` accepts an active-low trigger and
`;eyes=OS` relabels the channels. The RS-232 link on the preamp stays for
setting gain/filters.

You don't have to write the string by hand: on the Live page, pick `nidaq`
and open **DAQ 연결 도우미**. *장치 찾기* lists the NI devices attached to the
PC (`GET /api/live/daq` — name, model, serial, AI channels, ranges, max rate);
choose the OD/OS/trigger channels, gain and filters, and it builds and
applies the connection string (warning on channel clashes or a rate above the
device's limit). The last driver/connection is remembered per PC.

**Bench check (장비 점검).** The Live page commissions a new rig without
extra tools: per-channel RMS / peak-to-peak noise and the mains (60/50 Hz)
component; trigger rate and interval jitter (is the stimulator TTL wired?);
and **CAL-pulse gain calibration** — press the amplifier's CAL button, enter
the CAL amplitude and *CAL 측정* measures the pulse on each channel; if the
reading is off, *게인 보정 적용* writes the corrected per-channel gain
(`gain × measured / expected`) into the connection string and reconnects. If
the gain is unknown, start with `gain=1`; the CAL step finds it.

**Recording from the live stream.** The Live page's *검사로 저장* panel stores
the trigger-synchronised running average as a protocol step of an exam
(`POST /api/exams/record`): the epoch is resampled onto the step's sampling
rate/duration, so the standard marker detection, laboratory reference ranges
and report apply unchanged. With OD and OS channels, *OU (양안 동시)* stores both
eyes from the same sweeps. Further steps/eyes can be appended to the same exam.
Epochs start only on a trigger; choosing a step sets the epoch length to the
step's duration and the artifact limit to the step's default (120 µV p-p for
PERG/VEP), and sweeps exceeding it (blinks, movement) are rejected and counted
in the exam note.

### Laboratory normative data

ISCEV requires each laboratory to establish its own reference ranges. They
live in the database (`reference_ranges`, optionally per age band) and are
managed at **/reference** (role `manage_reference`: admin, clinician): edit
rows, import a CSV of ranges, or upload normal-subject measurements
(`step_key,marker,latency_ms,amplitude_uv`) and compute limits as mean ± 2 SD
or 5–95th percentiles. Judgement uses the row matching the patient's age;
the built-in demonstration values are seeded on first start (source `demo`)
and should be replaced before clinical use.

A WebSocket (`/ws/live`) streams samples (one row per channel), marks trigger
positions and reports live impedance to the **Live** page, which shows a scrolling oscilloscope,
**trigger-synchronised running average** (noise falls as √N) and a per-electrode
**impedance monitor** (ISCEV < 5 kΩ). Selecting a real driver only requires its
transport `read` loop; the host side (ring buffer, epoching, averaging, live
view) is already provided.

## Security & access control

The application requires a login and enforces role-based access:

| Role | Patients | Exams | Full national id (PHI) | Users / audit |
|------|----------|-------|------------------------|---------------|
| **admin** | view / edit / delete | run / delete | ✓ | ✓ |
| **clinician** | view / edit / delete | run / delete | ✓ | — |
| **technician** | view / edit | run | — (masked only) | — |
| **viewer** | view | view reports | — | — |

- **PHI at rest** — the national id (주민등록번호) is encrypted with Fernet and
  only ever returned masked (e.g. `720815-2******`). The full value comes from
  a separate `view_phi`-only endpoint, and every reveal is written to the
  audit log.
- **Passwords** are stored as PBKDF2-HMAC-SHA256 hashes; sessions are signed
  cookies (`SessionMiddleware`). Users change their own password at `/account`.
- **Brute-force lockout** — an account is locked for 15 minutes after 5
  consecutive failed logins.
- **Two-factor authentication (TOTP)** — optional per user; enrol at
  `/account` (QR for Google Authenticator / Authy). Login then requires the
  6-digit code.
- **Audit log** records logins (incl. lockouts and 2FA failures), record
  *views* (`patient.view` / `exam.view`), patient/exam changes, PHI views and
  account changes; admins review it at `/admin` and export it to CSV.
- On first start an **admin** account is seeded (`ADMIN_USERNAME` /
  `ADMIN_PASSWORD`) — change the password immediately.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `DATABASE_URL` | `sqlite:///./ophthal_electrophysiology.db` | database |
| `ACQUISITION_DRIVER` | `simulator` | active device driver |
| `DEVICE_CONNECTION` | `sim://localhost` | driver connection string |
| `SECRET_KEY` | `dev-insecure-change-me` | signs session cookies — **set in production** |
| `PHI_ENCRYPTION_KEY` | derived from `SECRET_KEY` | Fernet key for PHI at rest |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | `admin` / `admin1234` | seeded initial admin |
| `SESSION_HTTPS_ONLY` | `0` | set `1` behind HTTPS |

> **Note:** reference ranges in `app/iscev/reference.py` are representative
> demonstration values. Each laboratory must substitute its own normative
> data before clinical use.
>
> **Production hardening:** set strong `SECRET_KEY` and `PHI_ENCRYPTION_KEY`,
> serve over HTTPS with `SESSION_HTTPS_ONLY=1`, and manage the encryption key
> with a secrets manager (rotating it requires re-encrypting stored PHI).
