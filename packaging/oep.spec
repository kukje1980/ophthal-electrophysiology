# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the standalone build.

Run from the repository root:

    pyinstaller packaging/oep.spec --noconfirm

The result is dist/OphthalElectrophysiology/ with the executable, the
templates and static files it serves, and the Python runtime.
"""
import os
import sys

from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
sys.path.insert(0, ROOT)

hidden = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + [
        "PIL.Image",
        "PIL.ImageOps",
        "PIL.ExifTags",
        "qrcode.image.pil",
        "cryptography.fernet",
        "itsdangerous",
        "multipart",
        "python_multipart",
    ]
)

a = Analysis(
    [os.path.join(ROOT, "packaging", "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "templates"), "templates"),
        (os.path.join(ROOT, "static"), "static"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "IPython", "notebook"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="OphthalElectrophysiology",
    debug=False,
    strip=False,
    upx=False,
    console=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="OphthalElectrophysiology",
)
