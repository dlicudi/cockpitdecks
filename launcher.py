import hashlib
import os
import runpy
import sys


def _launcher_fingerprint() -> str:
    target = sys.executable if getattr(sys, "frozen", False) else __file__
    try:
        with open(target, "rb") as fp:
            digest = hashlib.sha1(fp.read()).hexdigest()[:12]
        mtime = int(os.path.getmtime(target))
        return f"path={target} sha1={digest} mtime={mtime}"
    except Exception as exc:
        return f"path={target} fingerprint_error={exc.__class__.__name__}"


if __name__ == "__main__":
    print(f"[launcher-fingerprint] {_launcher_fingerprint()}", flush=True)
    runpy.run_module("cockpitdecks.start", run_name="__main__")