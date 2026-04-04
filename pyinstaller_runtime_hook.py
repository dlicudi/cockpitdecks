import ctypes
import ctypes.util
import os
import sys


_ORIGINAL_CDLL_LOADLIBRARY = ctypes.cdll.LoadLibrary
_ORIGINAL_CDLL = ctypes.CDLL


def _prepend_env_path(name: str, value: str) -> None:
    current = os.environ.get(name, "")
    parts = [p for p in current.split(os.pathsep) if p]
    if value not in parts:
        parts.insert(0, value)
        os.environ[name] = os.pathsep.join(parts)


def _bundle_dir() -> str:
    return getattr(sys, "_MEIPASS", "")


def _register_windows_dll_dir(base_dir: str) -> None:
    if not base_dir or sys.platform != "win32":
        return

    _prepend_env_path("PATH", base_dir)
    add_dll_directory = getattr(os, "add_dll_directory", None)
    if add_dll_directory is not None:
        try:
            add_dll_directory(base_dir)
        except OSError as exc:
            print(f"[pyinstaller_runtime_hook] warning: failed to register DLL directory {base_dir}: {exc}", flush=True)


def _load_bundled_cairo() -> None:
    base_dir = _bundle_dir()
    if not base_dir:
        return

    if sys.platform == "darwin":
        _prepend_env_path("DYLD_FALLBACK_LIBRARY_PATH", base_dir)
        _prepend_env_path("DYLD_LIBRARY_PATH", base_dir)
    elif sys.platform == "win32":
        _register_windows_dll_dir(base_dir)

    cairo_aliases = {
        "cairo",
        "cairo-2",
        "libcairo-2",
        "libcairo",
    }
    cairo_candidates = [
        os.path.join(base_dir, "libcairo.2.dylib"),
        os.path.join(base_dir, "libcairo-2.dll"),
        os.path.join(base_dir, "cairo-2.dll"),
    ]
    cairo_path = next((path for path in cairo_candidates if os.path.exists(path)), "")

    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str):
        if name in cairo_aliases and cairo_path and os.path.exists(cairo_path):
            return cairo_path
        return original_find_library(name)

    ctypes.util.find_library = _patched_find_library

    if sys.platform == "darwin":
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
    elif sys.platform == "win32":
        preload_order = [
            "libwinpthread-1.dll",
            "libgcc_s_seh-1.dll",
            "libstdc++-6.dll",
            "zlib1.dll",
            "libbz2-1.dll",
            "libbrotlicommon.dll",
            "libbrotlidec.dll",
            "libpng16-16.dll",
            "libfreetype-6.dll",
            "libexpat-1.dll",
            "libintl-8.dll",
            "libiconv-2.dll",
            "libgraphite2.dll",
            "libharfbuzz-0.dll",
            "libfontconfig-1.dll",
            "libpcre2-8-0.dll",
            "libffi-8.dll",
            "libglib-2.0-0.dll",
            "libgobject-2.0-0.dll",
            "libgmodule-2.0-0.dll",
            "libgthread-2.0-0.dll",
            "libgio-2.0-0.dll",
            "libpixman-1-0.dll",
            "libcairo-2.dll",
            "libcairo-gobject-2.dll",
        ]
    else:
        preload_order = []

    for name in preload_order:
        path = os.path.join(base_dir, name)
        if not os.path.exists(path):
            continue
        try:
            if sys.platform == "win32":
                ctypes.WinDLL(path)
            else:
                ctypes.CDLL(path, mode=ctypes.RTLD_GLOBAL)
        except OSError as exc:
            print(f"[pyinstaller_runtime_hook] warning: failed to preload {name}: {exc}", flush=True)


def _load_bundled_hidapi() -> None:
    base_dir = _bundle_dir()
    if not base_dir:
        return

    if sys.platform == "darwin":
        _prepend_env_path("DYLD_FALLBACK_LIBRARY_PATH", base_dir)
        _prepend_env_path("DYLD_LIBRARY_PATH", base_dir)
    elif sys.platform == "win32":
        _register_windows_dll_dir(base_dir)

    if sys.platform == "win32":
        for dependency_name in ("libusb-1.0.dll",):
            dependency_path = os.path.join(base_dir, dependency_name)
            if not os.path.exists(dependency_path):
                continue
            try:
                ctypes.WinDLL(dependency_path)
            except OSError as exc:
                print(f"[pyinstaller_runtime_hook] warning: failed to preload {dependency_name}: {exc}", flush=True)

    hidapi_candidates = [
        os.path.join(base_dir, "libhidapi.0.dylib"),
        os.path.join(base_dir, "libhidapi.dylib"),
        os.path.join(base_dir, "libhidapi-0.dll"),
        os.path.join(base_dir, "libhidapi.dll"),
        os.path.join(base_dir, "hidapi.dll"),
    ]
    hidapi_path = next((p for p in hidapi_candidates if os.path.exists(p)), None)
    if not hidapi_path:
        return

    hidapi_aliases = {
        "hidapi",
        "hidapi.dll",
        "hidapi-libusb",
        "libhidapi",
        "libhidapi.dll",
        "libhidapi-0",
        "libhidapi-0.dll",
        "libhidapi.0",
    }

    original_find_library = ctypes.util.find_library

    def _patched_find_library(name: str):
        if name in hidapi_aliases:
            return hidapi_path
        return original_find_library(name)

    ctypes.util.find_library = _patched_find_library

    def _resolve_hidapi_target(name):
        if isinstance(name, str):
            if name in hidapi_aliases:
                return hidapi_path
            basename = os.path.basename(name)
            if basename in hidapi_aliases:
                return hidapi_path
        return name

    def _patched_cdll_loadlibrary(name):
        return _ORIGINAL_CDLL_LOADLIBRARY(_resolve_hidapi_target(name))

    def _patched_cdll(name, *args, **kwargs):
        return _ORIGINAL_CDLL(_resolve_hidapi_target(name), *args, **kwargs)

    ctypes.cdll.LoadLibrary = _patched_cdll_loadlibrary
    ctypes.CDLL = _patched_cdll

    try:
        if sys.platform == "win32":
            ctypes.WinDLL(hidapi_path)
        else:
            ctypes.CDLL(hidapi_path, mode=ctypes.RTLD_GLOBAL)
    except OSError as exc:
        print(f"[pyinstaller_runtime_hook] warning: failed to preload {os.path.basename(hidapi_path)}: {exc}", flush=True)


_load_bundled_cairo()
_load_bundled_hidapi()
