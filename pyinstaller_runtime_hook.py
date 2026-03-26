import ctypes
import ctypes.util
import os
import sys


def _prepend_env_path(name: str, value: str) -> None:
    current = os.environ.get(name, "")
    parts = [p for p in current.split(os.pathsep) if p]
    if value not in parts:
        parts.insert(0, value)
        os.environ[name] = os.pathsep.join(parts)


def _load_bundled_cairo() -> None:
    base_dir = getattr(sys, "_MEIPASS", "")
    if not base_dir:
        return

    _prepend_env_path("DYLD_FALLBACK_LIBRARY_PATH", base_dir)
    _prepend_env_path("DYLD_LIBRARY_PATH", base_dir)

    cairo_aliases = {
        "cairo",
        "cairo-2",
        "libcairo-2",
        "libcairo",
    }
    cairo_path = os.path.join(base_dir, "libcairo.2.dylib")

    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str):
        if name in cairo_aliases and os.path.exists(cairo_path):
            return cairo_path
        return original_find_library(name)

    ctypes.util.find_library = _patched_find_library

    preload_order = [
        "libpng16.16.dylib",
        "libfreetype.6.dylib",
        "libfontconfig.1.dylib",
        "libXau.6.dylib",
        "libXdmcp.6.dylib",
        "libxcb.1.dylib",
        "libxcb-render.0.dylib",
        "libxcb-shm.0.dylib",
        "libX11.6.dylib",
        "libXext.6.dylib",
        "libXrender.1.dylib",
        "libpixman-1.0.dylib",
        "libglib-2.0.0.dylib",
        "libgobject-2.0.0.dylib",
        "libcairo.2.dylib",
        "libcairo-gobject.2.dylib",
    ]

    for name in preload_order:
        path = os.path.join(base_dir, name)
        if not os.path.exists(path):
            continue
        try:
            ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            print(f"[pyinstaller_runtime_hook] warning: failed to preload {name}: {exc}", flush=True)


def _load_bundled_hidapi() -> None:
    base_dir = getattr(sys, "_MEIPASS", "")
    if not base_dir:
        return

    _prepend_env_path("DYLD_FALLBACK_LIBRARY_PATH", base_dir)
    _prepend_env_path("DYLD_LIBRARY_PATH", base_dir)

    hidapi_path = os.path.join(base_dir, "libhidapi.dylib")
    if not os.path.exists(hidapi_path):
        return

    hidapi_aliases = {
        "hidapi",
        "hidapi-libusb",
        "libhidapi",
    }

    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str):
        if name in hidapi_aliases:
            return hidapi_path
        return original_find_library(name)

    ctypes.util.find_library = _patched_find_library

    try:
        ctypes.CDLL(hidapi_path, mode=ctypes.RTLD_GLOBAL)
    except OSError as exc:
        print(f"[pyinstaller_runtime_hook] warning: failed to preload libhidapi.dylib: {exc}", flush=True)


_load_bundled_cairo()
_load_bundled_hidapi()
