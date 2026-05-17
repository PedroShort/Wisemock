"""WiseMock — local exam practice app.

Public API:
    from wisemock import main             # run the app
    from wisemock.app import main         # same, explicit module
    python -m wisemock                    # launch from CLI

The Qt env-var defaults below MUST be set before any Qt module is imported
anywhere in the package. Putting them in this `__init__.py` guarantees they
run first, since Python evaluates the package init before any submodule.
"""
import os as _os
import sys as _sys
_os.environ.setdefault("QT_OPENGL", "software")
_os.environ.setdefault("QT_QUICK_BACKEND", "software")
_chromium_flags = _os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
for _flag in (
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--autoplay-policy=no-user-gesture-required",
):
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
if _sys.platform.startswith("win"):
    # Keep WebEngine content from being enlarged by Windows DPI scaling.
    _flag = "--force-device-scale-factor=1"
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
_os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags
del _chromium_flags, _flag, _os, _sys


def main():
    """Launch the WiseMock GUI. Lazy-imports the Qt stack on first call."""
    from wisemock.app import main as _main
    _main()


__all__ = ["main"]
