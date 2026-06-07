# Ophthalmic Electrophysiology (ISCEV ERG / VEP)

A FastAPI + web application for recording, analysing and reporting clinical
visual electrophysiology studies following the **ISCEV** standards:

| Test  | Protocols |
|-------|-----------|
| **ffERG** | DA 0.01, DA 3.0, DA 10.0, dark-adapted oscillatory potentials, LA 3.0, LA 30 Hz flicker |
| **PERG**  | transient pattern ERG (N35 / P50 / N95) |
| **VEP**   | pattern-reversal (N75 / P100 / N135), flash VEP |
| **mfERG** | 61- and 103-hexagon arrays |

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
templates/  static/  Jinja2 pages + Canvas plotting
```

## Real-device integration

The application never talks to hardware directly — it talks to the abstract
`AcquisitionDevice` contract in `app/acquisition/base.py`. A built-in
`SimulatedDevice` generates ISCEV-realistic waveforms so the full pipeline
works out of the box.

To plug in a real recorder:

1. **Implement a driver** — subclass `AcquisitionDevice` and implement
   `connect`, `disconnect`, `configure(protocol)` and
   `acquire_step(step, eye)` using your vendor SDK / serial / TCP transport.
   Return an `AcquiredTrace` (eye, step, sampling_rate, duration_ms, samples).

2. **Register it**:

   ```python
   from app.acquisition import register_driver
   register_driver("my_recorder", MyRecorderDevice)
   ```

3. **Select it** via environment variables — no other code changes:

   ```bash
   export ACQUISITION_DRIVER=my_recorder
   export DEVICE_CONNECTION="/dev/ttyUSB0"   # or "192.168.0.10:5025"
   python run.py
   ```

The `/api/devices` endpoints expose the registry and live device status, and
`crud.run_exam` drives whichever driver is active. Everything above the
acquisition layer (models, analysis, UI, reports) is unchanged whether the
data comes from the simulator or real hardware.

## Configuration

| Env var | Default | Purpose |
|---------|---------|---------|
| `DATABASE_URL` | `sqlite:///./ophthal_electrophysiology.db` | database |
| `ACQUISITION_DRIVER` | `simulator` | active device driver |
| `DEVICE_CONNECTION` | `sim://localhost` | driver connection string |

> **Note:** reference ranges in `app/iscev/reference.py` are representative
> demonstration values. Each laboratory must substitute its own normative
> data before clinical use.
