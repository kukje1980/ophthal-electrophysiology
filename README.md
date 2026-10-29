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

## Clinical photos — 전체사진 + 멀티 뷰어

Fundus, red-free, FAF, FAG, ICGA, OCT/OCT-A, anterior segment, topography and
visual-field images can be stored per patient (**전체사진** in the top bar, or
the *사진* section of a patient).

- **Upload** — drag & drop several files at once with eye (OD/OS/OU),
  modality, date and a note. JPEG / PNG / WebP / BMP / GIF are kept exactly as
  uploaded; TIFF and other formats (incl. 16-bit) are converted to lossless PNG
  for the browser. A blank date falls back to the file's EXIF capture time.
- **전체사진** — every photo as a thumbnail grid grouped by date, filterable by
  patient / modality / eye. Click to select (Shift+click for a range, *이 날짜
  선택* for a whole visit); the selection is kept across searches, so photos of
  different patients or visits can be combined.
- **▦ 멀티** opens the selected photos side by side (auto 1 / 1×2 / 2×2 / 2×3 /
  3×3 layout; extra photos wait in the filmstrip — click one to show it in the
  selected viewport, the same photo may be shown twice to compare filters).
  On each viewport, while looking at the photo:
  - **확대 / 이동** — wheel or pinch zoom at the cursor (to 3200 %), drag to pan,
    *맞춤* / *1:1*, double-click to enlarge one viewport, **🔗 동기화** to zoom
    and pan every viewport together (OD vs OS, follow-up comparison);
  - **🔍 돋보기** magnifier lens (wheel changes its power);
  - **회전 / 반전** — 90° rotation, horizontal / vertical flip;
  - **영상 조정** — brightness, contrast, gamma, saturation, sharpen, auto
    levels, **Red-free** (green channel), R / B / grey channels, invert, with a
    live histogram; *모든 사진에 적용* copies the settings to every viewport;
  - **📏 측정** — length lines in pixels, or µm/mm once a µm/px scale is set;
    cursor position and original RGB are read out;
  - **3D** — WebGL surface of the (adjusted) image with brightness as height:
    orbit / pan / zoom, height and smoothing, mesh resolution, texture /
    height-colour-map / shaded surface, grid, auto-rotate.
  - **⬇ 내려받기** saves the edited image (or 3D view); **💾 편집본 저장** stores
    it as a *new* photo linked to the original (`source_id`) — originals are
    never modified.

  Large images stay responsive: adjustments preview on a ≤1.5 MP proxy while a
  slider moves and are applied at full resolution once it rests. Keyboard
  shortcuts are listed under **?** in the viewer.

**Storage & privacy.** Image files live under `PHOTO_DIR`, encrypted at rest
with the PHI Fernet key and named by random keys (no patient data on disk);
deleting a photo or its patient removes the files after the transaction
commits. Every full-image view / download is written to the audit log
(`photo.view`, `photo.download`, `photo.upload`, `photo.edit_save`,
`photo.delete`).

| Endpoint | Purpose |
|----------|---------|
| `GET /api/photos` | list (`patient_id`, `q`, `modality`, `eye`, or `ids=1,2,3` in order) |
| `POST /api/photos` | multipart upload (`patient_id`, `files[]`, `eye`, `modality`, `taken_at`, `note`, `source_id`) |
| `GET /api/photos/{id}/image` | full image (`?download=1` for the original file) |
| `GET /api/photos/{id}/thumb` | JPEG thumbnail |
| `PUT` / `DELETE /api/photos/{id}` | edit metadata / delete |

## Architecture

```
app/
  main.py            FastAPI app
  config.py          settings (env-overridable)
  database.py        SQLAlchemy engine/session
  models/            Patient, Exam, Waveform, Measurement
  schemas/           Pydantic I/O
  crud/              DB access + acquire→store→auto-mark pipeline
  routers/           patients, exams, photos, protocols, devices, pages (HTML)
  iscev/             protocol catalogue, reference ranges, marker detection
  acquisition/       device abstraction (the hardware seam)
    amplifier.py     biopotential amplifier contract
    stimulator.py    visual stimulator contract
    base.py          AcquisitionDevice + CompositeDevice (averaging loop)
    simulator.py     simulated amplifier + stimulator (default driver)
    hardware.py      ready-to-fill skeleton for a real rig
    registry.py      driver registry + active-device selection
templates/  static/  Jinja2 pages + Canvas plotting; static/js/photo-viewer.js
                     is the multi-photo viewer (2D canvas + WebGL 3D)
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
| `sim-stream` | built-in | wall-clock-paced ERG signal (no hardware) |
| `lsl` | functional | Lab Streaming Layer — BioSemi / g.tec / Brain Products / OpenBCI (needs `pylsl`) |
| `biosemi-tcp` | functional | BioSemi ActiveTwo raw TCP stream |
| `serial-csv` | functional | generic serial ASCII samples (needs `pyserial`) |
| `nidaq` | functional | NI-DAQmx analog input — digitiser for an **analog preamplifier (e.g. Grass P511 / CP511 / Model 15)**; optional trigger channel + gain→µV (needs `nidaqmx`) |
| `gtec` / `ced` | skeleton | vendor SDK required |

**Analog preamplifier (Grass, etc.) via a DAQ:** wire the amplifier's BNC
outputs to the DAQ analog inputs (ch0 = OD, ch1 = OS) and, optionally, the
stimulator TTL into a spare input as the trigger. Select the `nidaq` driver
with e.g. `Dev1/ai0,Dev1/ai1@2000;gain=10000;trig=Dev1/ai7;thr=1.0`
(`gain` = the preamp gain, used to refer samples back to input µV). Add
`;diff=1` for differential inputs (common-mode rejection), `;notch=60` for a
stateful mains notch and `;hp=0.3` for DC/baseline removal
(`app/acquisition/filters.py`). The RS-232 link on the preamp stays for
setting gain/filters.

**Recording from the live stream.** The Live page's *검사로 저장* panel stores
the trigger-synchronised running average as a protocol step of an exam
(`POST /api/exams/record`): the epoch is resampled onto the step's sampling
rate/duration, so the standard marker detection, laboratory reference ranges
and report apply unchanged. Further steps/eyes can be appended to the same exam.

### Laboratory normative data

ISCEV requires each laboratory to establish its own reference ranges. They
live in the database (`reference_ranges`, optionally per age band) and are
managed at **/reference** (role `manage_reference`: admin, clinician): edit
rows, import a CSV of ranges, or upload normal-subject measurements
(`step_key,marker,latency_ms,amplitude_uv`) and compute limits as mean ± 2 SD
or 5–95th percentiles. Judgement uses the row matching the patient's age;
the built-in demonstration values are seeded on first start (source `demo`)
and should be replaced before clinical use.

A WebSocket (`/ws/live`) streams samples, marks trigger positions and reports
live impedance to the **Live** page, which shows a scrolling oscilloscope,
**trigger-synchronised running average** (noise falls as √N) and a per-electrode
**impedance monitor** (ISCEV < 5 kΩ). Selecting a real driver only requires its
transport `read` loop; the host side (ring buffer, epoching, averaging, live
view) is already provided.

## Security & access control

The application requires a login and enforces role-based access:

| Role | Patients | Exams | Photos | Full national id (PHI) | Users / audit |
|------|----------|-------|--------|------------------------|---------------|
| **admin** | view / edit / delete | run / delete | view / upload / delete | ✓ | ✓ |
| **clinician** | view / edit / delete | run / delete | view / upload / delete | ✓ | — |
| **technician** | view / edit | run | view / upload | — (masked only) | — |
| **viewer** | view | view reports | view | — | — |

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
| `PHOTO_DIR` | `./data/photos` | encrypted clinical photo store |
| `PHOTO_MAX_MB` | `40` | upload limit per image file |

> **Note:** reference ranges in `app/iscev/reference.py` are representative
> demonstration values. Each laboratory must substitute its own normative
> data before clinical use.
>
> **Production hardening:** set strong `SECRET_KEY` and `PHI_ENCRYPTION_KEY`,
> serve over HTTPS with `SESSION_HTTPS_ONLY=1`, and manage the encryption key
> with a secrets manager (rotating it requires re-encrypting stored PHI, including the photo store).
