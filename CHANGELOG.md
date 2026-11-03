# Changelog

## v0.3.0 — 2026-11-03

첫 정식 릴리즈. 2026-10-04 이후의 모든 작업 브랜치를 통합한 버전입니다.
First tagged release, integrating every working branch since 2026-10-04.

### 검사 흐름 / Clinical workflow
- **검사 접수 (reception) start screen** with per-visit records and fast patient search.
- **Two-eye live recording**, DAQ auto-detect and bench checks for real acquisition rigs.
- **Reading workflow**: cursor editing, interocular (OD/OS) asymmetry analysis, interpretation text and report sign-off.
- **Manual marker review**: snap-to-peak, rod b-wave search window, polarity sign rule.
- Lab reference ranges, live-stream exam recording and DAQ noise filters.

### 임상 사진 / Clinical photos
- **전체사진 (photo gallery)** per patient: fundus, red-free, FAF, FAG, ICGA, OCT/OCT-A, anterior segment, topography, visual field.
- **멀티 뷰어**: synchronized zoom/pan across viewports, magnifier, rotation/flip, image adjustments with live histogram, red-free/channel views, length measurement, WebGL 3D surface view, edited-copy saving.
- The Windows fundus-camera viewer moved to its own repository: [kukje1980/Image-capture](https://github.com/kukje1980/Image-capture).

### 사용자 인터페이스 / UI
- Redesigned as an **instrument-grade console** (RetiCam 3100+ style) across all pages.

### 안정성 / Reliability
- Durable SQLite (WAL) database with verified scheduled **backups**, idempotency keys, structured logging, scaling and network-resilience settings.
- Authentication, RBAC, PHI encryption, audit logging, 2FA, account lockout, audit CSV export.

### 참고 문서 / Reference documents
- Market survey of skin (lower-lid) ERG electrodes with recommendation.
- Survey of dry and non-contact EEG electrode makers for gel-free VEP.

### 배포 / Distribution
- **Windows standalone build** (PyInstaller, no Python install needed) and a source zip,
  published automatically by the `release` workflow at the fixed address
  `releases/download/latest/…`; `v*` tags also get a permanent release.
- Templates and static files are resolved from the package location (`RESOURCE_DIR`),
  so the server no longer depends on the working directory.

### 기타 / Housekeeping
- Dependencies updated to current releases (FastAPI 0.162, SQLAlchemy 2.1, Pydantic 2.14, NumPy 2.5).
- Test suite: 58 tests (`python -m pytest`).
- Version string unified to `0.3.0` (`app.__version__`, OpenAPI `/docs`).

### 설치 / Install

```bash
pip install -r requirements.txt
python run.py
```

Open <http://localhost:8000>.
