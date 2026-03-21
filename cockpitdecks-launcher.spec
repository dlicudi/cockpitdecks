# cockpitdecks-launcher.spec

import os
import sys

sys.path.insert(0, os.path.abspath(os.getcwd()))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "xplane-webapi")))

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

datas = []
binaries = []
hiddenimports = []

for pkg in [
    "cockpitdecks",
    "cockpitdecks_xp",
    "cockpitdecks_ld",
    "cockpitdecks_sd",
    "cockpitdecks_wm",
    "cockpitdecks_ext",
    "avwx",
    "StreamDeck",
    "Loupedeck",
    "requests_cache",
]:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as e:
        print(f"collect_all failed for {pkg}: {e}")

# Explicit dynamic imports/backends
hiddenimports += [
    "mido.backends.rtmidi",
    "StreamDeck.ImageHelpers.PILHelper",
    "Loupedeck.Devices.LoupedeckLive",
    # Hardware drivers (collect_submodules can fail if import order hits a cycle)
    "cockpitdecks_ld.decks.loupedeck",
    "cockpitdecks_ld.buttons.representation",
    "cockpitdecks_sd.decks.streamdeck",
]

a = Analysis(
    ["launcher.py"],
    pathex=[
        os.path.abspath(os.getcwd()),
        os.path.abspath(os.path.join(os.getcwd(), "..", "xplane-webapi")),
    ],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="cockpitdecks-launcher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
