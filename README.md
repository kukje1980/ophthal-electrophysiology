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
  cookies (`SessionMiddleware`).
- **Audit log** records logins, patient/exam changes, PHI views and account
  changes; admins review it at `/admin`.
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
