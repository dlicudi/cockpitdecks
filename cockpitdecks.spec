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
BUNDLED_BINARY_PATHS = set()

_ROOT = os.path.abspath(os.getcwd())
_WORKSPACE = os.path.abspath(os.path.join(_ROOT, ".."))
_IS_WINDOWS = sys.platform == "win32"
_IS_MACOS = sys.platform == "darwin"


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
            if candidate in BUNDLED_BINARY_PATHS:
                print(f"[launcher.spec] already bundled {description}: {candidate}")
                return candidate
            binaries.append((candidate, "."))
            BUNDLED_BINARY_PATHS.add(candidate)
            print(f"[launcher.spec] bundling {description}: {candidate}")
            return candidate
    print(f"[launcher.spec] warning: {description} not found")
    return None


def _bundle_candidates(entries: list[tuple[str, list[str]]], group_name: str) -> None:
    print(f"[launcher.spec] scanning {group_name}")
    for description, candidates in entries:
        _bundle_first_existing(candidates, description)


def _bundle_all_matching(directory: str, suffix: str, group_name: str) -> None:
    directory = _real(directory)
    if not os.path.isdir(directory):
        print(f"[launcher.spec] warning: {group_name} directory not found: {directory}")
        return

    print(f"[launcher.spec] bundling all {suffix} files from {directory} for {group_name}")
    count = 0
    for name in sorted(os.listdir(directory)):
        if not name.lower().endswith(suffix.lower()):
            continue
        path = _real(os.path.join(directory, name))
        if path in BUNDLED_BINARY_PATHS:
            continue
        binaries.append((path, "."))
        BUNDLED_BINARY_PATHS.add(path)
        count += 1
    print(f"[launcher.spec] bundled {count} files from {directory}")


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

if _IS_MACOS:
    # Bundle libhidapi (required by StreamDeck for USB HID access).
    _bundle_candidates(
        [
            ("libhidapi.0.dylib", ["/opt/homebrew/opt/hidapi/lib/libhidapi.0.dylib", "/usr/local/opt/hidapi/lib/libhidapi.0.dylib"]),
            ("libhidapi.dylib", ["/opt/homebrew/lib/libhidapi.dylib", "/usr/local/lib/libhidapi.dylib"]),
        ],
        "macOS HID libraries",
    )

    # Bundle Cairo and its direct native dependencies used by CairoSVG/cairocffi on macOS.
    _bundle_candidates(
        [
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
        ],
        "macOS Cairo libraries",
    )
elif _IS_WINDOWS:
    # First-pass Windows packaging uses GTK/MSYS2-provided Cairo and hidapi DLLs when present.
    _WINDOWS_DLL_ROOTS = [
        os.environ.get("PYINSTALLER_DLL_DIR"),
        r"C:\msys64\mingw64\bin",
        r"C:\msys64\ucrt64\bin",
        r"C:\Program Files\GTK3-Runtime Win64\bin",
        r"C:\gtk\bin",
    ]
    _WINDOWS_DLL_ROOTS = [root for root in _WINDOWS_DLL_ROOTS if root]

    def _win_candidates(*names: str) -> list[str]:
        return [os.path.join(root, name) for root in _WINDOWS_DLL_ROOTS for name in names]

    _bundle_candidates(
        [
            ("hidapi.dll", _win_candidates("hidapi.dll", "libhidapi-0.dll", "libhidapi.dll")),
        ],
        "Windows HID libraries",
    )

    _bundle_candidates(
        [
            ("cairo DLL", _win_candidates("libcairo-2.dll", "cairo-2.dll")),
            ("cairo-gobject DLL", _win_candidates("libcairo-gobject-2.dll", "cairo-gobject-2.dll")),
            ("pixman DLL", _win_candidates("libpixman-1-0.dll", "pixman-1-0.dll")),
            ("png DLL", _win_candidates("libpng16-16.dll", "libpng16.dll")),
            ("fontconfig DLL", _win_candidates("libfontconfig-1.dll", "fontconfig-1.dll")),
            ("freetype DLL", _win_candidates("libfreetype-6.dll", "freetype-6.dll")),
            ("glib DLL", _win_candidates("libglib-2.0-0.dll", "glib-2.0-0.dll")),
            ("gobject DLL", _win_candidates("libgobject-2.0-0.dll", "gobject-2.0-0.dll")),
            ("gio DLL", _win_candidates("libgio-2.0-0.dll")),
            ("gmodule DLL", _win_candidates("libgmodule-2.0-0.dll")),
            ("gthread DLL", _win_candidates("libgthread-2.0-0.dll")),
            ("ffi DLL", _win_candidates("libffi-8.dll", "libffi-7.dll")),
            ("expat DLL", _win_candidates("libexpat-1.dll", "expat.dll")),
            ("gettext intl DLL", _win_candidates("libintl-8.dll")),
            ("iconv DLL", _win_candidates("libiconv-2.dll")),
            ("harfbuzz DLL", _win_candidates("libharfbuzz-0.dll")),
            ("graphite2 DLL", _win_candidates("libgraphite2.dll")),
            ("pcre2 DLL", _win_candidates("libpcre2-8-0.dll")),
            ("zlib DLL", _win_candidates("zlib1.dll")),
            ("brotli common DLL", _win_candidates("libbrotlicommon.dll", "brotlicommon.dll")),
            ("brotli dec DLL", _win_candidates("libbrotlidec.dll", "brotlidec.dll")),
            ("bz2 DLL", _win_candidates("libbz2-1.dll", "bz2.dll")),
            ("gcc runtime DLL", _win_candidates("libgcc_s_seh-1.dll", "libgcc_s_dw2-1.dll")),
            ("stdc++ runtime DLL", _win_candidates("libstdc++-6.dll")),
            ("winpthread DLL", _win_candidates("libwinpthread-1.dll")),
        ],
        "Windows Cairo libraries",
    )

    # First-pass safety net: bundle the full MSYS2/GTK DLL directory used for Cairo.
    for _dll_root in _WINDOWS_DLL_ROOTS:
        _bundle_all_matching(_dll_root, ".dll", f"Windows DLL fallback from {_dll_root}")

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
