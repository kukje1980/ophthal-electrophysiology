# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the desktop build (macOS .app / Windows folder).

    pyinstaller --noconfirm --clean packaging/ophthal.spec

Run from the repository root. Icons are optional: generate them first with
``python packaging/make_icons.py packaging/build-icons``.
"""
import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve().parent
sys.path.insert(0, str(ROOT))
from app import __version__ as VERSION  # noqa: E402

NAME = "OphthalElectrophysiology"
BUNDLE_ID = "com.kukje.ophthal-electrophysiology"
ICON_DIR = ROOT / "packaging" / "build-icons"
icon = None
if sys.platform == "darwin" and (ICON_DIR / "icon.icns").exists():
    icon = str(ICON_DIR / "icon.icns")
elif sys.platform == "win32" and (ICON_DIR / "icon.ico").exists():
    icon = str(ICON_DIR / "icon.ico")

hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + [
        "sqlalchemy.dialects.sqlite",
        "qrcode.image.svg",
        "PIL.Image", "PIL.ImageOps", "PIL.ExifTags",
        "multipart", "python_multipart",
        "anyio._backends._asyncio",
    ]
)

a = Analysis(
    [str(ROOT / "desktop.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "static"), "static"),
        (str(ROOT / "templates"), "templates"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tests", "pytest", "matplotlib", "scipy", "pandas", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # the Tk control window is the UI; logs go to the data folder
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name=f"{NAME}.app",
        icon=icon,
        bundle_identifier=BUNDLE_ID,
        version=VERSION,
        info_plist={
            "CFBundleName": NAME,
            "CFBundleDisplayName": "Ophthal Electrophysiology",
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHumanReadableCopyright": "Kukje Eye Clinic",
            # the server accepts LAN connections; the sandbox is not used
            "NSLocalNetworkUsageDescription": "다른 PC/태블릿에서 검사 화면에 접속할 수 있도록 로컬 네트워크를 사용합니다.",
        },
    )
