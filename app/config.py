"""Application configuration.

All settings can be overridden via environment variables, which keeps the
real-device deployment decoupled from the source code.
"""
import os


class Settings:
    # Database -------------------------------------------------------------
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", "sqlite:///./ophthal_electrophysiology.db"
    )

    # Acquisition device ---------------------------------------------------
    # Which acquisition driver to use. "simulator" is the built-in default.
    # A real hardware driver can register itself in the driver registry and
    # be selected here (e.g. ACQUISITION_DRIVER=diagnosys_espion) without any
    # code change in the rest of the application.
    ACQUISITION_DRIVER: str = os.getenv("ACQUISITION_DRIVER", "simulator")

    # Free-form connection string passed to the selected driver
    # (e.g. a serial port "/dev/ttyUSB0", a TCP "192.168.0.10:5025", ...).
    DEVICE_CONNECTION: str = os.getenv("DEVICE_CONNECTION", "sim://localhost")

    APP_TITLE: str = "Ophthalmic Electrophysiology (ISCEV ERG/VEP)"

    # Security -------------------------------------------------------------
    # Signs the session cookie. MUST be set to a strong random value in
    # production (e.g. `python -c "import secrets;print(secrets.token_hex(32))"`).
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-insecure-change-me")

    # Fernet key (urlsafe base64, 32 bytes) used to encrypt PHI such as the
    # national id at rest. If unset, a key is derived from SECRET_KEY so the
    # demo works out of the box; set an explicit key in production.
    PHI_ENCRYPTION_KEY: str = os.getenv("PHI_ENCRYPTION_KEY", "")

    # Password for the auto-seeded initial admin account (created only when no
    # users exist). Change immediately after first login.
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin1234")

    SESSION_COOKIE: str = os.getenv("SESSION_COOKIE", "oep_session")
    # Set to "1" behind HTTPS so the session cookie is only sent over TLS.
    SESSION_HTTPS_ONLY: bool = os.getenv("SESSION_HTTPS_ONLY", "0") == "1"


settings = Settings()
