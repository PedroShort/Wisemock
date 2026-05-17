"""Application entry point — wires QApplication, style, and the main window."""
import os
import sys

# QtWebEngine can crash on some macOS + Conda GPU stacks. These must be set
# before importing any Qt modules so `python -m wisemock` gets the same
# software-rendering safeguards as the legacy `wiseflow.py` launcher.
os.environ.setdefault("QT_OPENGL", "software")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
_chromium_flags = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
for _flag in (
    "--disable-gpu",
    "--disable-gpu-compositing",
    "--autoplay-policy=no-user-gesture-required",
):
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
if sys.platform.startswith("win"):
    # Some Windows QtWebEngine builds apply the OS DPI scale inside Chromium,
    # making the HTML UI look zoomed-in even when the QMainWindow fits.
    _flag = "--force-device-scale-factor=1"
    if _flag not in _chromium_flags:
        _chromium_flags = f"{_chromium_flags} {_flag}".strip()
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = _chromium_flags
del _chromium_flags, _flag

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication

from wisemock.config import WEB_FRONTEND_AVAILABLE
from wisemock.pages.setup import SetupWindow
from wisemock.runtime.windows import WebFrontendWindow
from wisemock.style import STYLE


def main():
    # HiDPI scaling MUST be enabled before QApplication is instantiated.
    # Without these, Windows displays at 125/150% scaling render the WebEngine
    # frontend small or blurry. macOS Retina already scales correctly.
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Arial", 11))
    window = WebFrontendWindow() if WEB_FRONTEND_AVAILABLE else SetupWindow()
    window.show()
    app.exec_()
