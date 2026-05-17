"""Top-level QMainWindow that hosts the HTML/JS frontend + bridge."""
from PyQt5.QtCore import QUrl
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWidgets import QMainWindow, QMessageBox

from wisemock.config import ASSETS_DIR
from wisemock.runtime.bridge import FrontendBridge
from wisemock.runtime.geometry import fit_window_to_screen, web_zoom_for_screen
from wisemock.runtime.web_view import FrontendWebView

FRONTEND_HTML = ASSETS_DIR / "wisemock_frontend.html"


class WebFrontendWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("WiseMock")
        self.view = FrontendWebView(self)
        self.view.setZoomFactor(web_zoom_for_screen(self))
        self.bridge = FrontendBridge(self)
        self.channel = QWebChannel(self.view.page())
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)
        self.view.file_dropped.connect(self.bridge.handleDroppedFile)
        self.view.files_dropped.connect(self.bridge.handleDroppedFiles)
        self.setCentralWidget(self.view)
        fit_window_to_screen(self, preferred_size=(1180, 860), minimum_size=(760, 560))
        self._load_frontend()

    def _load_frontend(self):
        if not FRONTEND_HTML.exists():
            QMessageBox.critical(self, "Missing frontend", f"Could not find frontend file:\n{FRONTEND_HTML}")
            return
        self.view.load(QUrl.fromLocalFile(str(FRONTEND_HTML.resolve())))
