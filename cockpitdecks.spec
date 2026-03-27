# cockpitdecks.spec

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


def _bundle_first_existing(candidates: list[str], description: str) -> str | None:
    for candidate in candidates:
        candidate = _real(candidate)
        if os.path.exists(candidate):
            binaries.append((candidate, "."))
            print(f"[launcher.spec] bundling {description}: {candidate}")
            return candidate
    print(f"[launcher.spec] warning: {description} not found")
    return None


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
for _description, _candidates in [
    ("libhidapi.0.dylib", ["/opt/homebrew/opt/hidapi/lib/libhidapi.0.dylib", "/usr/local/opt/hidapi/lib/libhidapi.0.dylib"]),
    ("libhidapi.dylib", ["/opt/homebrew/lib/libhidapi.dylib", "/usr/local/lib/libhidapi.dylib"]),
]:
    _bundle_first_existing(_candidates, _description)

# Bundle Cairo and its direct native dependencies used by CairoSVG/cairocffi on macOS.
for _description, _candidates in [
    ("libcairo.2.dylib", ["/opt/homebrew/lib/libcairo.2.dylib", "/usr/local/lib/libcairo.2.dylib"]),
    ("libcairo-gobject.2.dylib", ["/opt/homebrew/lib/libcairo-gobject.2.dylib", "/usr/local/lib/libcairo-gobject.2.dylib"]),
    ("libpixman-1.0.dylib", ["/opt/homebrew/opt/pixman/lib/libpixman-1.0.dylib", "/usr/local/opt/pixman/lib/libpixman-1.0.dylib"]),
    ("libpng16.16.dylib", ["/opt/homebrew/opt/libpng/lib/libpng16.16.dylib", "/usr/local/opt/libpng/lib/libpng16.16.dylib"]),
    ("libfontconfig.1.dylib", ["/opt/homebrew/opt/fontconfig/lib/libfontconfig.1.dylib", "/usr/local/opt/fontconfig/lib/libfontconfig.1.dylib"]),
    ("libfreetype.6.dylib", ["/opt/homebrew/opt/freetype/lib/libfreetype.6.dylib", "/usr/local/opt/freetype/lib/libfreetype.6.dylib"]),
    ("libX11.6.dylib", ["/opt/homebrew/opt/libx11/lib/libX11.6.dylib", "/usr/local/opt/libx11/lib/libX11.6.dylib"]),
    ("libXext.6.dylib", ["/opt/homebrew/opt/libxext/lib/libXext.6.dylib", "/usr/local/opt/libxext/lib/libXext.6.dylib"]),
    ("libXrender.1.dylib", ["/opt/homebrew/opt/libxrender/lib/libXrender.1.dylib", "/usr/local/opt/libxrender/lib/libXrender.1.dylib"]),
    ("libxcb.1.dylib", ["/opt/homebrew/opt/libxcb/lib/libxcb.1.dylib", "/usr/local/opt/libxcb/lib/libxcb.1.dylib"]),
    ("libxcb-render.0.dylib", ["/opt/homebrew/opt/libxcb/lib/libxcb-render.0.dylib", "/usr/local/opt/libxcb/lib/libxcb-render.0.dylib"]),
    ("libxcb-shm.0.dylib", ["/opt/homebrew/opt/libxcb/lib/libxcb-shm.0.dylib", "/usr/local/opt/libxcb/lib/libxcb-shm.0.dylib"]),
    ("libXau.6.dylib", ["/opt/homebrew/opt/libxau/lib/libXau.6.dylib", "/usr/local/opt/libxau/lib/libXau.6.dylib"]),
    ("libXdmcp.6.dylib", ["/opt/homebrew/opt/libxdmcp/lib/libXdmcp.6.dylib", "/usr/local/opt/libxdmcp/lib/libXdmcp.6.dylib"]),
    ("libglib-2.0.0.dylib", ["/opt/homebrew/opt/glib/lib/libglib-2.0.0.dylib", "/usr/local/opt/glib/lib/libglib-2.0.0.dylib"]),
    ("libgobject-2.0.0.dylib", ["/opt/homebrew/opt/glib/lib/libgobject-2.0.0.dylib", "/usr/local/opt/glib/lib/libgobject-2.0.0.dylib"]),
]:
    _bundle_first_existing(_candidates, _description)

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
    runtime_hooks=[os.path.abspath(os.path.join(os.getcwd(), "pyinstaller_runtime_hook.py"))],
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
    name="cockpitdecks",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
