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


settings = Settings()
