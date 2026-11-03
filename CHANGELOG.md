# Changelog

All notable changes to the ERG/VEP application are listed here.
Versions follow [Semantic Versioning](https://semver.org/); the running
version is reported by `/health` and shown in the `/docs` title.

## [0.2.0] — 2026-11-03

First tagged release of the ISCEV ERG / VEP system.

### Acquisition (검사)
- ISCEV-conformant protocols: ffERG 2022 (DA 0.01 / DA 3 / DA 10 / OPs /
  LA 3 / 30 Hz flicker), PERG 2024, VEP 2025 (N75 / P100 / N145, flash VEP),
  mfERG 2021 (61- and 103-hexagon).
- Monitor stimulator screen incl. multifocal hexagon stimulus.
- Real-device streaming: amplifier + stimulator interfaces, trigger-synced
  averaging, live impedance, DAQ noise filters, NI-DAQmx stream driver for
  analog preamplifiers (e.g. Grass via DAQ), DAQ auto-detect and bench checks.
- Two-eye live recording with a live WebSocket oscilloscope and artifact
  rejection.

### Reading & reporting (판독)
- Automatic standard-marker detection (a/b-wave, OPs, N35 / P50 / N95,
  N75 / P100 / N145, N1 / P1 / N2) with implicit time and amplitude.
- Manual marker review: cursor editing, snap to peak, rod b-wave window,
  sign rule.
- Lab reference ranges, interocular analysis, PERG N95:P50 ratio.
- Interpretation text and physician sign-off; printable reports.

### Reception & records (검사 접수 · 기록)
- Reception start screen with fast patient search, ophthalmic EMR-style
  registration, per-visit records and worklist.
- Soft delete (trash) and restore for patients and exams.

### Clinical photos (전체사진 · 멀티 뷰어)
- Per-patient image store for fundus, red-free, FAF, FAG, ICGA, OCT / OCT-A,
  anterior segment, topography and visual-field images.
- Multi viewer with 3D looks and image tools.
- The Windows fundus-camera viewer moved to
  [kukje1980/Image-capture](https://github.com/kukje1980/Image-capture).

### Security & access control
- Login sessions, role-based access control, PHI encryption at rest,
  audit logging with CSV export and access logs.
- Password change, 2FA, account lockout.

### Reliability & data safety
- Durable SQLite (WAL) with safe schema upgrades, verified scheduled
  backups, graceful shutdown, network-resilience settings for flaky LANs.
- Idempotent writes and retry-friendly handling of a locked database.

### UI
- Instrument-grade console redesign (RetiCam 3100+ style).
- Standalone interactive preview (no server required) under `preview/`.

### Docs
- Market surveys of skin (lower-lid) ERG electrodes and of dry / non-contact
  EEG electrodes for gel-free VEP under `docs/`.

[0.2.0]: https://github.com/kukje1980/ophthal-electrophysiology/releases/tag/v0.2.0
