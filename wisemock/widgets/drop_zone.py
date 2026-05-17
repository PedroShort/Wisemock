"""Drop-zone widget for selecting / dropping study files and exam JSON."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout,
)

from wisemock.config import SUPPORTED_DOC_EXTENSIONS
from wisemock.widgets.helpers import _restyle_widget


class DropZone(QFrame):
    file_dropped = pyqtSignal(str)
    files_dropped = pyqtSignal(list)
    ACCEPTED_EXTENSIONS = (".json",) + SUPPORTED_DOC_EXTENSIONS

    def __init__(self):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._loaded = False
        self._inner = QVBoxLayout(self)
        self._inner.setContentsMargins(10, 10, 10, 10)
        self._inner.setSpacing(0)
        self.setCursor(Qt.PointingHandCursor)
        self._show_empty()

    def _is_accepted(self, path: str) -> bool:
        return any(path.lower().endswith(ext) for ext in self.ACCEPTED_EXTENSIONS)

    def _make_icon_box(self, text, bg="#f7f7f7", border="#d0d0d0", color="#aaa", font_size=20):
        box = QFrame()
        box.setFixedSize(52, 52)
        box.setStyleSheet(
            f"background: {bg}; border: 1px solid {border}; border-radius: 12px;"
        )
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"font-size: {font_size}px; color: {color}; background: transparent; border: none;")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(lbl)
        return box

    def _show_empty(self):
        self._clear()
        row = QHBoxLayout()
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(20)
        icon_box = self._make_icon_box("↑")
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        main_lbl = QLabel("Drop study files or WiseMock JSON here")
        main_lbl.setObjectName("DropMainText")
        sub_lbl = QLabel("PDF/DOCX/PPTX generate exams. JSON loads a saved WiseMock exam.")
        sub_lbl.setObjectName("DropSubText")
        text_col.addWidget(main_lbl)
        text_col.addWidget(sub_lbl)
        row.addWidget(icon_box)
        row.addLayout(text_col, 1)
        self._inner.addLayout(row)

    def _show_loaded(self, filename: str, n: int, types: list):
        self._clear()
        row = QHBoxLayout()
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(20)
        icon_box = self._make_icon_box("✓", bg="#eafaf1", border="#82d8a0", color="#27ae60", font_size=24)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(filename)
        name.setObjectName("FileNameLabel")
        type_counts = {}
        for t in types:
            type_counts[t] = type_counts.get(t, 0) + 1
        summary = "  ·  ".join(f"{v} {k}" for k, v in type_counts.items())
        meta = QLabel(f"{n} question{'s' if n != 1 else ''}   ({summary})")
        meta.setObjectName("FileMetaLabel")
        text_col.addWidget(name)
        text_col.addWidget(meta)
        row.addWidget(icon_box)
        row.addLayout(text_col, 1)
        self._inner.addLayout(row)

    def _show_doc_loaded(self, filename: str):
        self._clear()
        row = QHBoxLayout()
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(20)
        icon_box = self._make_icon_box("↑", bg="#f0f7ff", border="#a0c4e8", color="#4a90c4")
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        name = QLabel(filename)
        name.setObjectName("FileNameLabel")
        hint = QLabel("Configure options below, then generate")
        hint.setObjectName("FileMetaLabel")
        text_col.addWidget(name)
        text_col.addWidget(hint)
        row.addWidget(icon_box)
        row.addLayout(text_col, 1)
        self._inner.addLayout(row)

    def _show_loading(self, percent: int, message: str):
        self._clear()
        row = QHBoxLayout()
        row.setContentsMargins(12, 12, 12, 12)
        row.setSpacing(20)
        icon_box = self._make_icon_box(f"{max(0, min(100, int(percent)))}%", bg="#fff8e8", border="#e4c46c", color="#8a6a12", font_size=14)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("Loading document...")
        title.setObjectName("FileNameLabel")
        hint = QLabel(message or "Extracting text in the background")
        hint.setObjectName("FileMetaLabel")
        hint.setWordWrap(True)
        text_col.addWidget(title)
        text_col.addWidget(hint)
        row.addWidget(icon_box)
        row.addLayout(text_col, 1)
        self._inner.addLayout(row)

    def set_loading(self, percent: int, message: str):
        self._loaded = True
        self._set_style("DropZoneLoaded")
        self._show_loading(percent, message)

    def set_doc_loaded(self, filename: str):
        self._loaded = True
        self._set_style("DropZoneLoaded")
        self._show_doc_loaded(filename)

    def _clear(self):
        while self._inner.count():
            item = self._inner.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.setParent(None)
                w.deleteLater()

    def _set_style(self, name: str):
        self.setObjectName(name)
        _restyle_widget(self)

    def set_loaded(self, filename: str, n: int, types: list):
        self._loaded = True
        self._set_style("DropZoneLoaded")
        self._show_loaded(filename, n, types)

    def reset(self):
        self._loaded = False
        self._set_style("DropZone")
        self._show_empty()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            filter_str = (
                "All supported (*.json *.pdf *.docx *.pptx);;"
                "JSON files (*.json);;PDF files (*.pdf);;"
                "Word documents (*.docx);;PowerPoint (*.pptx);;All files (*)"
            )
            paths, _ = QFileDialog.getOpenFileNames(self, "Select file(s)", "", filter_str)
            if len(paths) == 1:
                self.file_dropped.emit(paths[0])
            elif paths:
                self.files_dropped.emit(paths)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            if any(self._is_accepted(u.toLocalFile()) for u in event.mimeData().urls()):
                event.acceptProposedAction()
                self._set_style("DropZoneHover")

    def dragLeaveEvent(self, event):
        self._set_style("DropZoneLoaded" if self._loaded else "DropZone")

    def dropEvent(self, event):
        self._set_style("DropZoneLoaded" if self._loaded else "DropZone")
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path:
                paths.append(path)
        if len(paths) == 1:
            self.file_dropped.emit(paths[0])
        elif paths:
            self.files_dropped.emit(paths)
