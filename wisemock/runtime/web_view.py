"""QWebEngineView subclass that emits dropped local files via `file_dropped`."""
import sys
import traceback

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWebEngineWidgets import QWebEngineView


class FrontendWebView(QWebEngineView):
    file_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
            else:
                super().dragEnterEvent(event)
        except Exception:
            # Never let a drag event crash the Qt loop.
            traceback.print_exc(file=sys.stderr)

    def dropEvent(self, event):
        try:
            if event.mimeData().hasUrls():
                paths = []
                for url in event.mimeData().urls():
                    local_path = url.toLocalFile()
                    if local_path and isinstance(local_path, str) and local_path.strip():
                        paths.append(local_path.strip())
                if len(paths) == 1:
                    self.file_dropped.emit(paths[0])
                elif paths:
                    self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
            super().dropEvent(event)
        except Exception:
            # Defensive: a malformed drag/drop must never crash the app. Log to
            # stderr so it shows up in the dev console without breaking UX.
            traceback.print_exc(file=sys.stderr)
            try:
                event.ignore()
            except Exception:
                pass
