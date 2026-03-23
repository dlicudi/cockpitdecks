# cockpitdecks-launcher.spec

import os
import sys
import importlib

sys.path.insert(0, os.path.abspath(os.getcwd()))
sys.path.insert(0, os.path.abspath(os.path.join(os.getcwd(), "..", "xplane-webapi")))

from PyInstaller.utils.hooks import collect_all, collect_submodules

block_cipher = None

datas = []
binaries = []
hiddenimports = []

_ROOT = os.path.abspath(os.getcwd())
_WORKSPACE = os.path.abspath(os.path.join(_ROOT, ".."))


def _real(path: str) -> str:
    return os.path.realpath(os.path.abspath(path))


def _is_under(path: str, root: str) -> bool:
    p = _real(path)
    r = _real(root)
    try:
        return os.path.commonpath([p, r]) == r
    except ValueError:
        return False


def _module_file(module_name: str) -> str:
    mod = importlib.import_module(module_name)
    mod_file = getattr(mod, "__file__", None)
    if not mod_file:
        raise RuntimeError(f"cannot resolve file for module {module_name!r}")
    return _real(mod_file)


def _assert_local_imports():
    expected_roots = {
        "cockpitdecks": os.path.join(_WORKSPACE, "cockpitdecks"),
        "cockpitdecks_xp": os.path.join(_WORKSPACE, "cockpitdecks_xp"),
        "cockpitdecks_ld": os.path.join(_WORKSPACE, "cockpitdecks_ld"),
        "cockpitdecks_sd": os.path.join(_WORKSPACE, "cockpitdecks_sd"),
        "cockpitdecks_wm": os.path.join(_WORKSPACE, "cockpitdecks_wm"),
        "cockpitdecks_ext": os.path.join(_WORKSPACE, "cockpitdecks_ext"),
        "cockpitdecks_bx": os.path.join(_WORKSPACE, "cockpitdecks_bx"),
        "xpwebapi": os.path.join(_WORKSPACE, "xplane-webapi"),
        "Loupedeck": os.path.join(_WORKSPACE, "python-loupedeck-live"),
    }
    failures = []
    resolved = {}
    for mod_name, expected_root in expected_roots.items():
        mod_path = _module_file(mod_name)
        resolved[mod_name] = mod_path
        if not _is_under(mod_path, expected_root):
            failures.append((mod_name, mod_path, _real(expected_root)))

    print("Launcher preflight import roots:")
    for mod_name in sorted(resolved):
        print(f"  {mod_name:16s} -> {resolved[mod_name]}")

    if failures:
        lines = ["Preflight failed: non-local imports detected (expected editable workspace checkouts):"]
        for mod_name, mod_path, expected_root in failures:
            lines.append(f"  - {mod_name}: {mod_path} (expected under {expected_root})")
        raise RuntimeError("\n".join(lines))


_assert_local_imports()

for pkg in [
    "cockpitdecks",
    "cockpitdecks_xp",
    # Explicit: always bundle from the same import path as `python -c "import xpwebapi"` (editable or not).
    "xpwebapi",
    "cockpitdecks_ld",
    "cockpitdecks_sd",
    "cockpitdecks_wm",
    "cockpitdecks_ext",
    "cockpitdecks_bx",
    "xtouchmini",
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
    "cockpitdecks_bx.decks.xtouchmini",
    "cockpitdecks_bx.buttons.representation",
]

# Bundle libhidapi (required by StreamDeck for USB HID access).
for _hidapi_path in [
    "/opt/homebrew/lib/libhidapi.dylib",
    "/usr/local/lib/libhidapi.dylib",
]:
    if os.path.exists(_hidapi_path):
        binaries.append((_hidapi_path, "."))
        print(f"[launcher.spec] bundling libhidapi: {_hidapi_path}")
        break
else:
    print("[launcher.spec] warning: libhidapi.dylib not found — Stream Deck will not work in frozen builds")

a = Analysis(
    ["launcher.py"],
    pathex=[
        os.path.abspath(os.getcwd()),
        os.path.abspath(os.path.join(os.getcwd(), "..", "xplane-webapi")),
        os.path.abspath(os.path.join(os.getcwd(), "..", "cockpitdecks_bx")),
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
