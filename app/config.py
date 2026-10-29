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

    # Real-time streaming (live monitor). Driver names: simulator "sim-stream",
    # "lsl", "biosemi-tcp", "serial-csv", "nidaq", "gtec", "ced".
    LIVE_STREAM_DRIVER: str = os.getenv("LIVE_STREAM_DRIVER", "sim-stream")
    STREAM_CONNECTION: str = os.getenv("STREAM_CONNECTION", "")

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

    # Server -----------------------------------------------------------------
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))
    # Auto-reload is for development only: it restarts the server on every
    # file change, which must never happen in the middle of an exam.
    RELOAD: bool = os.getenv("RELOAD", "0") == "1"

    # Database durability / pooling -------------------------------------------
    # SQLite synchronous level: FULL survives power loss without losing a
    # committed transaction (WAL mode keeps it fast). NORMAL is faster but a
    # power cut may drop the last commits.
    SQLITE_SYNCHRONOUS: str = os.getenv("SQLITE_SYNCHRONOUS", "FULL").upper()
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))

    # Backups ----------------------------------------------------------------
    BACKUP_ENABLED: bool = os.getenv("BACKUP_ENABLED", "1") == "1"
    BACKUP_DIR: str = os.getenv("BACKUP_DIR", "./backups")
    # A second copy on another disk / NAS / USB. Without it a disk failure
    # loses the database and its backups together.
    BACKUP_MIRROR_DIR: str = os.getenv("BACKUP_MIRROR_DIR", "")
    # A backup is taken whenever the newest one is older than this, so a PC
    # that is switched off at night still gets backed up the next morning.
    BACKUP_INTERVAL_HOURS: float = float(os.getenv("BACKUP_INTERVAL_HOURS", "6"))
    # Retention: every backup of the last N days, then the newest per day,
    # then the newest per month. Pre-restore / pre-migration safety copies
    # are never pruned automatically.
    BACKUP_KEEP_ALL_DAYS: int = int(os.getenv("BACKUP_KEEP_ALL_DAYS", "3"))
    BACKUP_KEEP_DAILY_DAYS: int = int(os.getenv("BACKUP_KEEP_DAILY_DAYS", "30"))
    BACKUP_KEEP_MONTHLY: int = int(os.getenv("BACKUP_KEEP_MONTHLY", "24"))
    # Free space that must remain on the backup disk after a backup, so a
    # backup can never fill the disk the live database is on.
    BACKUP_MIN_FREE_MB: int = int(os.getenv("BACKUP_MIN_FREE_MB", "500"))

    # Logging ----------------------------------------------------------------
    LOG_DIR: str = os.getenv("LOG_DIR", "./logs")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()


settings = Settings()
