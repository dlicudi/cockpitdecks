# Serialize PIL/FreeType operations for free-threaded Python compatibility.
# FreeType is not thread-safe; concurrent font rendering causes OSError: invalid outline.
import threading

PIL_RENDER_LOCK = threading.RLock()
